---
license: mit
task_categories:
- question-answering
language:
- pt
pretty_name: MATH-PT
size_categories:
- 1K<n<10K
configs:
- config_name: ptbr_multiple_choice
  data_files:
  - split: test
    path: ptbr_multiple_choice_test.json

- config_name: ptpt_multiple_choice
  data_files:
  - split: test
    path: ptpt_multiple_choice_test.json

- config_name: ptbr_open_ended
  data_files:
  - split: test
    path: ptbr_open_ended_test.json

- config_name: ptpt_open_ended
  data_files:
  - split: test
    path: ptpt_open_ended_test.json
---
# Math-PT: A Math Reasoning Benchmark for European and Brazilian Portuguese

Math-PT is a high-quality evaluation dataset designed to measure the mathematical reasoning capabilities of Large Language Models (LLMs) in Portuguese. 
Unlike many existing benchmarks that rely on English translations, Math-PT uses native-language problems sourced from prestigious academic competitions and national exams in both Portugal and Brazil.

## Dataset Details

### Dataset Description

Math-PT addresses the lack of high-fidelity mathematical evaluation resources for the Portuguese language. It specifically bridges the gap between European (pt-PT) and Brazilian (pt-BR) variants, ensuring that models are tested on linguistically idiomatic content rather than machine-translated English problems.

- **Created by:** Tiago Teixeira, Ana Carolina Erthal, Juan Belieni, Beatriz Canaverde, Miguel Faria, Diego Mesquita, Eliezer de Souza da Silva, André Martins
- **Language(s) (NLP):** PT-PT, PT-BR


## Dataset Structure

The dataset consists of 1,729 problems divided into four main configurations:
- ptbr_multiple_choice: Brazilian Portuguese multiple-choice questions.
- ptpt_multiple_choice: European Portuguese multiple-choice questions.
- ptbr_open_ended: Brazilian Portuguese open-ended (free-response) questions.
- ptpt_open_ended: European Portuguese open-ended (free-response) questions.
E
ach entry typically includes the problem statement, the correct answer, and (where applicable) the multiple-choice options.

## Dataset Creation

### Curation Rationale

Most mathematical reasoning benchmarks are English-centric. Even when translated, they often lose cultural context or linguistic nuances specific to Portuguese-speaking regions. Math-PT was created to provide a "native" evaluation ground using actual problems from the regions' educational systems.

### Source Data

The data was collected from authentic regional sources:
- Brazil: the Brazilian Mathematical Olympiad of Public Schools (Olimpíada Brasileira de Matemática das Escolas
Públicas, OBMEP), the Mathematics Olympiad of Federal Institutions (Olimpíada de Matemática
das Instituições Federais, OMIF), the Elon Lages Lima Mathematics Competition (Competição Elon Lages Lima de Matemática, ELLM) and the Entrance Exam for the Technological Institute of Aeronautics (Vestibular do Instituto Tecnológico de
Aeronáutica, ITA)
- Portugal: Problems from Portuguese Mathematics Olympiad (OPM).


## Citation 
Please cite the following publication if you use this dataset. 

**BibTeX:**
```
@inproceedings{mathpt.propor2026,
  title        = {Math-PT: A Math Reasoning Benchmark for European and Brazilian Portuguese},
  author       = {Tiago Teixeira and Ana Carolina Erthal and Juan Belieni and Beatriz Canaverde and Miguel Faria and Diego Mesquita and Eliezer de Souza da Silva and André Martins},
  year         = 2026,
  month        = {April},
  booktitle    = {Proceedings of the 17th Conference on Computational Processing of Portuguese (PROPOR)},
  organization = {PROPOR}
}
```


