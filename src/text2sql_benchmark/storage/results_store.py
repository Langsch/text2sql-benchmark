from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class BenchmarkResult:
    instance_id: int
    db_id: str
    difficulty: str
    model: str
    sgbd: str
    sql_generated: str
    sql_gold: str
    execution_accuracy: bool
    exact_match: bool
    latency_ms: float
    explain_raw: str
    explain_parsed: dict
    # Prompt exato enviado ao modelo — necessario para reproduzir a rodada.
    prompt: str = ""
    error: str | None = None
    # Classifica a falha. Sem isso um timeout (query valida porem lenta), um
    # SQL invalido e uma queda de API viram todos "erro", e a analise nao
    # consegue separar limitacao do modelo de problema de infraestrutura.
    #   timeout      -> query valida, excedeu o limite (resultado de performance)
    #   sql_error    -> SQL invalido (falha de corretude do modelo)
    #   llm_error    -> a API do modelo falhou (refazer, nao e resultado)
    #   system_error -> infraestrutura (nao e resultado)
    error_type: str | None = None
    # Quanto a query rodou antes de ser abortada, quando error_type=timeout.
    timed_out_after_ms: float = 0.0
    # Tokens da chamada. A Etapa 1 nao os gravava, e sem eles nao havia como
    # recontar o consumo de saida por questao: a comparacao entre modelos
    # dependia de amostras avulsas e teve de ser retirada do relatorio.
    input_tokens: int = 0
    output_tokens: int = 0
    # True quando o provedor cortou a resposta por atingir o teto de tokens.
    # Sem isto o corte fica invisivel: o extrator devolve o SQL parcial, que
    # pode ate executar, e o registro parece integro. A Etapa 2 ja gravava.
    truncated: bool = False
    # Provedor upstream que atendeu a chamada (so via OpenRouter). Registrado
    # por questao para permitir verificar, depois da rodada, que a pinagem
    # valeu do inicio ao fim — sem isso nao da para afirmar na metodologia sob
    # que condicao o experimento correu.
    provider: str = ""


class ResultsStore:
    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._results: list[BenchmarkResult] = []
        self._run_id: str | None = None

    def begin(self, run_id: str) -> None:
        """Liga a persistencia incremental: cada add() passa a gravar o arquivo.

        Sem isso os resultados ficam so em memoria ate o fim da rodada, e uma
        queda na ultima combinacao perde a rodada inteira.
        """
        self._run_id = run_id

    def add(self, result: BenchmarkResult) -> None:
        self._results.append(result)
        if self._run_id:
            self.save(self._run_id)

    def save(self, run_id: str) -> Path:
        path = self._output_dir / f"{run_id}.json"
        payload = json.dumps(
            [asdict(r) for r in self._results], indent=2, ensure_ascii=False
        )
        # Grava num temporario e renomeia: rename e atomico no mesmo filesystem,
        # entao uma queda no meio da escrita nao deixa JSON truncado no lugar.
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
        return path

    def load(self, path: Path) -> list[BenchmarkResult]:
        data = json.loads(path.read_text(encoding="utf-8"))
        self._results = [BenchmarkResult(**d) for d in data]
        return self._results

    def descartar(self, *error_types: str) -> int:
        """Remove resultados dos tipos de erro dados. Devolve quantos saíram.

        Usado na retomada. Nem `llm_error` nem `system_error` sao resultado do
        modelo: o primeiro e chamada que nao aconteceu, o segundo e defeito do
        proprio benchmark. Os dois precisam sair antes de a questao ser refeita
        — senao o arquivo final teria a falha antiga e o resultado novo lado a
        lado. `sql_error` e `timeout` ficam: sao resultado e refaze-los
        mudaria a medicao.
        """
        alvos = set(error_types)
        antes = len(self._results)
        self._results = [r for r in self._results if r.error_type not in alvos]
        return antes - len(self._results)
