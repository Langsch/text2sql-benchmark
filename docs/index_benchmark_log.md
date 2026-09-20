# Log do Benchmark de Índices

> Registro das decisões, prompts utilizados e resultados obtidos no benchmark de sugestão de índices por LLMs.

---

## 1. Objetivo

Avaliar a capacidade dos LLMs de sugerir índices (CREATE INDEX) que melhorem a performance de queries SQL. O fluxo é:

1. Pegar as queries gold (referência) do BIRD para um banco
2. Enviar o schema + todas as queries para o LLM
3. Pedir CREATE INDEX statements
4. Aplicar os índices em uma cópia do banco
5. Medir latência e EXPLAIN QUERY PLAN antes vs depois

---

## 2. Prompt Utilizado

O template do prompt fica em `src/text2sql_benchmark/prompt/index_prompt.py`. A estrutura é:

```
[1] Instrução de papel
    "You are a database performance expert..."

[2] Schema do banco (DDL completo via sqlite_master)

[3] Todas as queries gold do BIRD para aquele db_id, numeradas

[4] Guidelines de análise
    - WHERE, JOIN ON, ORDER BY, GROUP BY
    - Índices compostos
    - Priorizar índices que beneficiem mais queries
    - Sintaxe SQLite

[5] Instrução de formato
    - Apenas CREATE INDEX, uma por linha
    - Sem explicações, sem markdown
    - Não criar índices em colunas que já são PRIMARY KEY
```

### Exemplo completo (student_club, 48 queries)

```sql
You are a database performance expert. Given the following SQLite database schema and a set of SQL queries that run against this database, suggest CREATE INDEX statements that would improve the performance of these queries.

-- Database: student_club

CREATE TABLE event
(
    event_id   TEXT
        constraint event_pk
            primary key,
    event_name TEXT,
    event_date TEXT,
    type       TEXT,
    notes      TEXT,
    location   TEXT,
    status     TEXT
)

CREATE TABLE major
(
    major_id   TEXT
        constraint major_pk
            primary key,
    major_name TEXT,
    department TEXT,
    college    TEXT
)

CREATE TABLE zip_code
(
    zip_code    INTEGER
        constraint zip_code_pk
            primary key,
    type        TEXT,
    city        TEXT,
    county      TEXT,
    state       TEXT,
    short_state TEXT
)

CREATE TABLE "attendance"
(
    link_to_event  TEXT,
    link_to_member TEXT,
    primary key (link_to_event, link_to_member),
    foreign key (link_to_event) references event(event_id),
    foreign key (link_to_member) references member(member_id)
)

CREATE TABLE "budget"
(
    budget_id     TEXT
            primary key,
    category      TEXT,
    spent         REAL,
    remaining     REAL,
    amount        INTEGER,
    event_status  TEXT,
    link_to_event TEXT,
    foreign key (link_to_event) references event(event_id)
)

CREATE TABLE "expense"
(
    expense_id          TEXT
            primary key,
    expense_description TEXT,
    expense_date        TEXT,
    cost                REAL,
    approved            TEXT,
    link_to_member      TEXT,
    link_to_budget      TEXT,
    foreign key (link_to_budget) references budget(budget_id),
    foreign key (link_to_member) references member(member_id)
)

CREATE TABLE "income"
(
    income_id      TEXT
        constraint income_pk
            primary key,
    date_received  TEXT,
    amount         INTEGER,
    source         TEXT,
    notes          TEXT,
    link_to_member TEXT,
    foreign key (link_to_member) references member(member_id)
)

CREATE TABLE "member"
(
    member_id     TEXT
        constraint member_pk
            primary key,
    first_name    TEXT,
    last_name     TEXT,
    email         TEXT,
    position      TEXT,
    t_shirt_size  TEXT,
    phone         TEXT,
    zip           INTEGER,
    link_to_major TEXT,
    foreign key (link_to_major) references major(major_id),
    foreign key (zip) references zip_code(zip_code)
)

## Queries

1. SELECT T2.major_name FROM member AS T1 INNER JOIN major AS T2 ON T1.link_to_major = T2.major_id WHERE T1.first_name = 'Angela' AND T1.last_name = 'Sanders'
2. SELECT COUNT(T1.event_id) FROM event AS T1 INNER JOIN attendance AS T2 ON T1.event_id = T2.link_to_event INNER JOIN member AS T3 ON T2.link_to_member = T3.member_id WHERE T1.event_name = 'Women''s Soccer' AND T3.t_shirt_size = 'Medium'
3. SELECT COUNT(DISTINCT T1.event_id) FROM event AS T1 INNER JOIN attendance AS T2 ON T1.event_id = T2.link_to_event WHERE T1.type = 'Meeting' GROUP BY T1.event_id HAVING COUNT(T2.link_to_event) > 10
4. SELECT T1.event_name FROM event AS T1 INNER JOIN attendance AS T2 ON T1.event_id = T2.link_to_event GROUP BY T1.event_id HAVING COUNT(T2.link_to_event) > 20 EXCEPT SELECT T1.event_name FROM event AS T1  WHERE T1.type = 'Fundraiser'
5. SELECT T2.amount FROM member AS T1 INNER JOIN income AS T2 ON T1.member_id = T2.link_to_member WHERE T1.position = 'Vice President'
6. SELECT T1.first_name, T1.last_name FROM member AS T1 INNER JOIN zip_code AS T2 ON T1.zip = T2.zip_code WHERE T2.state = 'Illinois'
7. SELECT T3.approved FROM event AS T1 INNER JOIN budget AS T2 ON T1.event_id = T2.link_to_event INNER JOIN expense AS T3 ON T2.budget_id = T3.link_to_budget WHERE T1.event_name = 'October Meeting' AND T1.event_date LIKE '2019-10-08%'
8. SELECT AVG(T2.cost) FROM member AS T1 INNER JOIN expense AS T2 ON T1.member_id = T2.link_to_member WHERE T1.last_name = 'Allen' AND T1.first_name = 'Elijah' AND (SUBSTR(T2.expense_date, 6, 2) = '09' OR SUBSTR(T2.expense_date, 6, 2) = '10')
9. SELECT SUM(CASE WHEN SUBSTR(T1.event_date, 1, 4) = '2019' THEN T2.spent ELSE 0 END) - SUM(CASE WHEN SUBSTR(T1.event_date, 1, 4) = '2020' THEN T2.spent ELSE 0 END) AS num FROM event AS T1 INNER JOIN budget AS T2 ON T1.event_id = T2.link_to_event
10. SELECT notes FROM income WHERE source = 'Fundraising' AND date_received = '2019-09-14'
11. SELECT phone FROM member WHERE first_name = 'Carlo' AND last_name = 'Jacobs'
12. SELECT T1.event_status FROM budget AS T1 INNER JOIN expense AS T2 ON T1.budget_id = T2.link_to_budget WHERE T2.expense_description = 'Post Cards, Posters' AND T2.expense_date = '2019-08-20'
13. SELECT T2.major_name FROM member AS T1 INNER JOIN major AS T2 ON T1.link_to_major = T2.major_id WHERE T1.first_name = 'Brent' AND T1.last_name = 'Thomason'
14. SELECT COUNT(T1.member_id) FROM member AS T1 INNER JOIN major AS T2 ON T1.link_to_major = T2.major_id WHERE T2.major_name = 'Business' AND T1.t_shirt_size = 'Medium'
15. SELECT T2.department FROM member AS T1 INNER JOIN major AS T2 ON T1.link_to_major = T2.major_id WHERE T1.position = 'President'
16. SELECT T2.date_received FROM member AS T1 INNER JOIN income AS T2 ON T1.member_id = T2.link_to_member WHERE T1.first_name = 'Connor' AND T1.last_name = 'Hilton' AND T2.source = 'Dues'
17. SELECT CAST(SUM(CASE WHEN T2.event_name = 'Yearly Kickoff' THEN T1.amount ELSE 0 END) AS REAL) / SUM(CASE WHEN T2.event_name = 'October Meeting' THEN T1.amount ELSE 0 END) FROM budget AS T1 INNER JOIN event AS T2 ON T1.link_to_event = T2.event_id WHERE T1.category = 'Advertisement' AND T2.type = 'Meeting'
18. SELECT SUM(cost) FROM expense WHERE expense_description = 'Pizza'
19. SELECT COUNT(city) FROM zip_code WHERE county = 'Orange County' AND state = 'Virginia'
20. SELECT T2.major_name FROM member AS T1 INNER JOIN major AS T2 ON T1.link_to_major = T2.major_id WHERE T1.phone = '809-555-3360'
21. SELECT COUNT(T2.link_to_member) FROM event AS T1 INNER JOIN attendance AS T2 ON T1.event_id = T2.link_to_event WHERE T1.event_name = 'Women''s Soccer'
22. SELECT T1.first_name, T1.last_name FROM member AS T1 INNER JOIN major AS T2 ON T1.link_to_major = T2.major_id WHERE T2.department = 'School of Applied Sciences, Technology and Education'
23. SELECT T2.event_name FROM budget AS T1 INNER JOIN event AS T2 ON T1.link_to_event = T2.event_id WHERE T2.status = 'Closed' ORDER BY T1.spent / T1.amount DESC LIMIT 1
24. SELECT MAX(spent) FROM budget
25. SELECT SUM(spent) FROM budget WHERE category = 'Food'
26. SELECT T1.first_name, T1.last_name FROM member AS T1 INNER JOIN attendance AS T2 ON T1.member_id = T2.link_to_member GROUP BY T2.link_to_member HAVING COUNT(T2.link_to_event) > 7
27. SELECT T4.first_name, T4.last_name FROM event AS T1 INNER JOIN budget AS T2 ON T1.event_id = T2.link_to_event INNER JOIN expense AS T3 ON T2.budget_id = T3.link_to_budget INNER JOIN member AS T4 ON T3.link_to_member = T4.member_id WHERE T1.event_name = 'Yearly Kickoff'
28. SELECT T1.event_name FROM event AS T1 INNER JOIN budget AS T2 ON T1.event_id = T2.link_to_event INNER JOIN expense AS T3 ON T2.budget_id = T3.link_to_budget ORDER BY T3.cost LIMIT 1
29. SELECT CAST(SUM(CASE WHEN T1.event_name = 'Yearly Kickoff' THEN T3.cost ELSE 0 END) AS REAL) * 100 / SUM(T3.cost) FROM event AS T1 INNER JOIN budget AS T2 ON T1.event_id = T2.link_to_event INNER JOIN expense AS T3 ON T2.budget_id = T3.link_to_budget
30. SELECT source FROM income WHERE date_received BETWEEN '2019-09-01' and '2019-09-30' ORDER BY source DESC LIMIT 1
31. SELECT COUNT(T2.member_id) FROM major AS T1 INNER JOIN member AS T2 ON T1.major_id = T2.link_to_major WHERE T1.major_name = 'Physics Teaching'
32. SELECT T2.event_name FROM budget AS T1 INNER JOIN event AS T2 ON T1.link_to_event = T2.event_id WHERE T1.category = 'Advertisement' ORDER BY T1.spent DESC LIMIT 1
33. SELECT CASE WHEN T3.event_name = 'Women''s Soccer' THEN 'YES' END AS result FROM member AS T1 INNER JOIN attendance AS T2 ON T1.member_id = T2.link_to_member INNER JOIN event AS T3 ON T2.link_to_event = T3.event_id WHERE T1.first_name = 'Maya' AND T1.last_name = 'Mclean'
34. SELECT T3.cost FROM event AS T1 INNER JOIN budget AS T2 ON T1.event_id = T2.link_to_event INNER JOIN expense AS T3 ON T2.budget_id = T3.link_to_budget WHERE T1.event_name = 'September Speaker' AND T3.expense_description = 'Posters'
35. SELECT T2.event_name FROM budget AS T1 INNER JOIN event AS T2 ON T2.event_id = T1.link_to_event WHERE T1.event_status = 'Closed' AND T1.remaining < 0 ORDER BY T1.remaining LIMIT 1
36. SELECT T1.type, SUM(T3.cost) FROM event AS T1 INNER JOIN budget AS T2 ON T1.event_id = T2.link_to_event INNER JOIN expense AS T3 ON T2.budget_id = T3.link_to_budget WHERE T1.event_name = 'October Meeting'
37. SELECT T2.category, SUM(T2.amount) FROM event AS T1 JOIN budget AS T2 ON T1.event_id = T2.link_to_event WHERE T1.event_name = 'April Speaker' GROUP BY T2.category ORDER BY SUM(T2.amount) ASC
38. SELECT SUM(cost) FROM expense WHERE expense_date = '2019-08-20'
39. SELECT T1.first_name, T1.last_name, SUM(T2.cost) FROM member AS T1 INNER JOIN expense AS T2 ON T1.member_id = T2.link_to_member WHERE T1.member_id = 'rec4BLdZHS2Blfp4v'
40. SELECT T2.expense_description FROM member AS T1 INNER JOIN expense AS T2 ON T1.member_id = T2.link_to_member WHERE T1.first_name = 'Sacha' AND T1.last_name = 'Harrison'
41. SELECT DISTINCT T2.category FROM event AS T1 INNER JOIN budget AS T2 ON T1.event_id = T2.link_to_event WHERE T1.location = 'MU 215'
42. SELECT T2.last_name, T1.department, T1.college FROM major AS T1 INNER JOIN member AS T2 ON T1.major_id = T2.link_to_major WHERE T2.position = 'Member' AND T1.major_name = 'Environmental Engineering'
43. SELECT DISTINCT T2.category, T1.type FROM event AS T1 INNER JOIN budget AS T2 ON T1.event_id = T2.link_to_event WHERE T1.location = 'MU 215' AND T2.spent = 0 AND T1.type = 'Guest Speaker'
44. SELECT CAST(SUM(CASE WHEN T2.amount = 50 THEN 1.0 ELSE 0 END) AS REAL) * 100 / COUNT(T2.income_id) FROM member AS T1 INNER JOIN income AS T2 ON T1.member_id = T2.link_to_member WHERE T1.position = 'Member' AND T1.t_shirt_size = 'Medium'
45. SELECT DISTINCT event_name FROM event WHERE type = 'Game' AND date(SUBSTR(event_date, 1, 10)) BETWEEN '2019-03-15' AND '2020-03-20' AND status = 'Closed'
46. SELECT DISTINCT T3.first_name, T3.last_name, T3.phone FROM expense AS T1 INNER JOIN budget AS T2 ON T1.link_to_budget = T2.budget_id INNER JOIN member AS T3 ON T3.member_id = T1.link_to_member WHERE T1.cost > ( SELECT AVG(T1.cost) FROM expense AS T1 INNER JOIN budget AS T2 ON T1.link_to_budget = T2.budget_id INNER JOIN member AS T3 ON T3.member_id = T1.link_to_member )
47. SELECT T2.first_name, T2.last_name, T1.cost FROM expense AS T1 INNER JOIN member AS T2 ON T1.link_to_member = T2.member_id WHERE T1.expense_description = 'Water, Veggie tray, supplies'
48. SELECT DISTINCT T3.first_name, T3.last_name, T4.amount FROM event AS T1 INNER JOIN attendance AS T2 ON T1.event_id = T2.link_to_event INNER JOIN member AS T3 ON T3.member_id = T2.link_to_member INNER JOIN income AS T4 ON T4.link_to_member = T3.member_id WHERE T4.date_received = '2019-09-09'

## Analysis guidelines
- Look at columns used in WHERE, JOIN ON, ORDER BY, and GROUP BY clauses.
- Consider composite indexes when multiple columns from the same table appear together in query conditions.
- Prioritize indexes that benefit the most queries.
- Use SQLite CREATE INDEX syntax.

Output ONLY the CREATE INDEX statements, one per line.
No explanations, no markdown code blocks, no comments.
Use the format: CREATE INDEX idx_<table>_<columns> ON <table>(<col1>, <col2>, ...);
Do NOT create indexes on columns that are already PRIMARY KEYs.
```

**Tamanho do prompt:** 11.726 caracteres, 48 queries.

---

## 3. Execução #1 — 2026-06-21

**Banco:** student_club
**Modelos:** llama-3.3-70b-versatile, qwen/qwen3-32b (ambos via Groq)
**Arquivo de resultados:** `results/runs/index_runs/20260621_165123_index_student_club.json`

### Resultados

| Modelo | Indexes Sugeridos | Aplicados | Falhou | Queries | Melhoraram | Novo Index Usado | Latência Antes (ms) | Latência Depois (ms) | Speedup |
|---|---|---|---|---|---|---|---|---|---|
| llama-3.3-70b-versatile | 27 | 27 | 0 | 48 | 38 (79.2%) | 9 | 0.18 | 0.07 | 2.44x |
| qwen/qwen3-32b | - | - | - | - | - | - | - | - | ERRO |

### Resposta do Llama (raw)

```sql
CREATE INDEX idx_member_link_to_major ON member(link_to_major)
CREATE INDEX idx_member_first_name_last_name ON member(first_name, last_name)
CREATE INDEX idx_event_event_name ON event(event_name)
CREATE INDEX idx_event_type ON event(type)
CREATE INDEX idx_event_event_id ON event(event_id)
CREATE INDEX idx_attendance_link_to_event ON attendance(link_to_event)
CREATE INDEX idx_attendance_link_to_member ON attendance(link_to_member)
CREATE INDEX idx_budget_link_to_event ON budget(link_to_event)
CREATE INDEX idx_expense_link_to_budget ON expense(link_to_budget)
CREATE INDEX idx_expense_link_to_member ON expense(link_to_member)
CREATE INDEX idx_income_link_to_member ON income(link_to_member)
CREATE INDEX idx_major_major_name ON major(major_name)
CREATE INDEX idx_zip_code_state ON zip_code(state)
CREATE INDEX idx_event_event_date ON event(event_date)
CREATE INDEX idx_expense_expense_date ON expense(expense_date)
CREATE INDEX idx_income_date_received ON income(date_received)
CREATE INDEX idx_member_position ON member(position)
CREATE INDEX idx_member_t_shirt_size ON member(t_shirt_size)
CREATE INDEX idx_member_phone ON member(phone)
CREATE INDEX idx_member_zip ON member(zip)
CREATE INDEX idx_major_department ON major(department)
CREATE INDEX idx_major_college ON major(college)
CREATE INDEX idx_budget_category ON budget(category)
CREATE INDEX idx_budget_event_status ON budget(event_status)
CREATE INDEX idx_expense_expense_description ON expense(expense_description)
CREATE INDEX idx_expense_cost ON expense(cost)
CREATE INDEX idx_zip_code_county ON zip_code(county)
```

### Erro do Qwen

O prompt com schema + 48 queries ficou com ~7470 tokens e estourou o limite do Groq no plano free (6000 TPM para qwen/qwen3-32b):

```
Error code: 413 - Request too large for model `qwen/qwen3-32b` ...
Limit 6000, Requested 7470
```

### Observações

- O Llama sugeriu 27 indexes e todos foram aplicados sem erro. Resposta limpa, sem explicações nem markdown — seguiu a instrução do prompt direitinho.
- O Llama criou `idx_event_event_id` que é redundante (event_id já é PK), mas o SQLite aceitou sem erro.
- 9 queries que antes faziam SCAN passaram a usar INDEX — o query planner do SQLite efetivamente aproveitou os índices sugeridos.
- 38 de 48 queries (79.2%) tiveram melhora de latência, com speedup médio de 2.44x.
- O banco student_club é pequeno (2.6MB), então as latências absolutas são sub-milissegundo. Bancos maiores (european_football_2 com 571MB) devem mostrar diferenças mais expressivas.
