# Live conversation transcript (real HTTP API, real local LLM)

Captured against the actual running `apps/results_chat` server (`http://127.0.0.1:8787`, Flask app + local llama-server at `http://127.0.0.1:8788`, Qwen2.5-1.5B-Instruct -- see `../model_provenance/MODEL_PROVENANCE.json`). Every turn below is a real network round-trip; `elapsed_seconds` is wall-clock time measured by the capturing script, not an estimate.

**Known limitation observed in this transcript**: in the `followup` turn, the local 1.5B model's Spanish generation contains a minor word substitution ("se frotó" instead of "se congeló", i.e. a garbled rendering of "was frozen") -- a real, unedited example of the small-model generation quality documented in `apps/results_chat/README.md`'s Limitations section. The transcript is shown verbatim, not corrected.

## greeting

- **Request**: `Hola` (session `review-bundle-transcript-2`)
- **Route/intent**: `social_greeting`
- **Answer mode**: `factual`
- **Response language**: `es`
- **Elapsed**: 0.013s
- **Citations**: (none -- purely social, no evidence claim made)

**Answer:**

> ¡Hola! Puedo explicarte los resultados de verificación RISC-V/TFLM de wafer_riscv_tflm (arquitectura, metodología, resultados, limitaciones) y generar gráficas a partir de ellos -- todo basado en la evidencia guardada del proyecto. Pregúntame lo que quieras, por ejemplo: "¿Está completo el experimento?" o "Grafica el F1 por clase."

## open_ended_spanish

- **Request**: `¿Puedes explicarme la metodología de verificación de este proyecto?` (session `review-bundle-transcript-2`)
- **Route/intent**: `open_ended_llm`
- **Answer mode**: `llm`
- **Response language**: `es`
- **Elapsed**: 26.662s
- **Citations**:
  - docs/decisions.md :: D-015: Social conversation (greetings/thanks/farewells/capability questions) answered without retrieval or citations
  - apps/results_chat/backend/knowledge/project_overview.md :: Verification methodology

**Answer:**

> ¡Por supuesto! La metodología de verificación de este proyecto se basa en dos aspectos principales: la verificación de la arquitectura y la verificación de la implementación en hardware.
> 
> 1. **Verificación de la arquitectura**: Se han realizado 9 pruebas dirigidas (ALU operaciones, x0, extensión del signo, desplazamientos, comparaciones, saltos, JAL/JALR, carga de bytes/halfword/word con isolación de las wait-states, cargas de memoria con wait-states, extensión completa del M y división por cero/overflow, 4 causas de error-halt distintas, un programa compilado en C) y todas han completado con éxito. Además, se han comparado 1100 instrucciones de un programa con un modelo de referencia independiente (`isa_reference_model.py`) que se utiliza en lugar de Spike, que no está instalada en este servidor. No se han encontrado errores en la implementación.
> 
> 2. **Verificación de la implementación en hardware**: Se han ejecutado 20 casos de prueba (5 por clase, seleccionados por el orden de el id de prueba dentro del split de prueba, después de que el modelo se frotó) en el procesador simulado RTL y comparados con la implementación en hardware. El resultado final, `full20_final_001`, incluye un exacto match de todos los cuatro puntos de salida y la pred

## followup

- **Request**: `¿Y cómo se comparó con el oráculo nativo?` (session `review-bundle-transcript-2`)
- **Route/intent**: `open_ended_llm`
- **Answer mode**: `llm`
- **Response language**: `es`
- **Elapsed**: 15.439s
- **Citations**:
  - apps/results_chat/backend/knowledge/project_overview.md :: Verification methodology
  - README.md :: 6. Native TFLM reference oracle
  - docs/handoff/claims_evidence.csv :: Claim C018 (measured)

**Answer:**

> La comparación con el oráculo nativo se hizo a través de 20 casos de prueba (5 por clase, seleccionados por el orden de el id de prueba dentro del split de prueba, después de que el modelo se frotó) en el procesador simulado RTL. Se compararon con la implementación en hardware. El resultado final, `full20_final_001`, incluye un exacto match de todos los cuatro puntos de salida y la predicción de la clase para cada caso, con un código de salida de 0.

## case_query

- **Request**: `What about case 16?` (session `review-bundle-transcript-2`, lang hint `en`)
- **Route/intent**: `case_lookup`
- **Answer mode**: `llm`
- **Response language**: `en`
- **Elapsed**: 15.715s
- **Citations**:
  - results/comparison_manifest.json (cases[*].sample_id, class_idx)
  - results/final_run_evidence/full20_final_001_check_report.json (rows[*], cases_parsed[*])
  - results/rtl_logs/full20_final_001_live.log (MMIO_PREDICTED_CLASS cycle=121534289 case_id=16)

**Answer:**

> Case 16 (sample_id 2276) had a ground truth of 'none'. The RTL predicted class 2 with scores [41, 10, 49, 49]. RTL vs native: MATCH. This is a misclassification relative to the ground truth. The RTL scores contain a tie: Scratch, none are both the maximum score (49); both RTL and the native oracle resolve it identically to class index 2, which is why they still agree exactly. Invoke() took 7,031,511 RTL cycles (start cycle 114502321, end cycle 121533832).

## chart_generation

- **Request**: `Plot F1 by class.` (session `review-bundle-transcript-2`, lang hint `en`)
- **Route/intent**: `chart`
- **Answer mode**: `factual`
- **Response language**: `en`
- **Elapsed**: 0.006s
- **Citations**:
  - results/ml_metrics.json (results.B.int8_metrics.test.per_class_f1)
- **Chart generated**: kind=`f1_by_class`, id=`7dc965cc0475ce287b12`, files: /api/chart/7dc965cc0475ce287b12.png | /api/chart/7dc965cc0475ce287b12.svg | /api/chart/7dc965cc0475ce287b12.csv

**Answer:**

> Per-class F1 for model B (int8), test split (macro-F1 = 0.77093).

## unavailable_measurement

- **Request**: `What was the chip's physical power consumption?` (session `review-bundle-transcript-2`, lang hint `en`)
- **Route/intent**: `physical_unsupported`
- **Answer mode**: `factual`
- **Response language**: `en`
- **Elapsed**: 0.004s
- **Citations**: (none -- explicit unsupported-data refusal)

**Answer:**

> The project's saved evidence does not contain that information. This project is an RTL simulation verification of a RISC-V processor; no synthesis, timing closure, or FPGA/silicon implementation was performed. Physical clock frequency, power consumption, and chip area were not measured -- those figures simply do not exist in this evidence.
