# Start here: wafer RISC-V and TensorFlow Lite Micro

This folder is the handoff package for Claude's implementation session. All project-authored material must be in English.

## Start the implementation

1. Make this entire folder accessible from Claude's Linux terminal, preserving its name: `wafer_riscv_tflm`.
2. Enable the Animas tools and allow Claude to read their documentation.
3. Open `claude_implementation_prompt.txt` and paste its complete contents as the initial instruction.
4. Let Claude inspect this folder, discover the real tool interfaces, prepare the software environment, and execute the project.

The prompt is already written. You do not need to provide RTL or a trained model. If Claude's working directory is this folder, it must use it directly rather than create another nested folder with the same name.

## Included files

- `claude_implementation_prompt.txt`: the complete implementation, verification, training, simulation, and evidence-capture instruction. Use this now.
- `setup_guide.md`: project setup and scope.
- `documentation_ai_prompt.txt`: a separate instruction for the later documentation-writing AI. Save it for after implementation.
- `scripts/download_dataset.py`: a dependency-free downloader for the public WM-811K archive; extracts only the dataset file and records checksums. It does not train a model or deserialize the pickle.
- `data/raw/README.md`: dataset description and expected location.
- `data/raw/LSWMD.pkl` and `data/raw/dataset_provenance.json`, when included: the downloaded real dataset and its recorded provenance.

Read `PACKAGE_CONTENTS.json` for the actual included-file inventory and checksums. An inventory confirms file packaging, not successful implementation of the processor or model.

## Windows and Linux paths

The requested Windows location is:

```text
C:\Users\matag\OneDrive\Documentos\git\wafer_riscv_tflm
```

For a local WSL environment with standard Windows-drive mounting, the corresponding path is normally:

```text
/mnt/c/Users/matag/OneDrive/Documentos/git/wafer_riscv_tflm
```

Claude must verify that the path exists and is readable in its own terminal. If Animas uses a remote Linux machine, transfer the entire folder there using the environment's existing file-transfer mechanism. Giving Claude a Windows path alone does not grant a remote machine access.

## If the dataset is missing

From the project root, the included helper can be run with:

```bash
python3 scripts/download_dataset.py
```

It uses Kaggle's public download endpoint, checks ZIP integrity during extraction, and records SHA-256 hashes. Availability can change. If access fails, follow the documented dataset download process; never replace the real data with synthetic data while claiming completion.

## Documentation comes later

The implementation prompt requires continuous development records and a project-specific handoff under `docs/handoff/`. Those files will be produced by Claude as it works. They are not fabricated in advance in this package.

After implementation, give the finished project and `documentation_ai_prompt.txt` to a separate AI session. The later writer must use actual findings, logs, decisions, experiments, and measured results, explicitly identifying missing or unsuccessful work.
