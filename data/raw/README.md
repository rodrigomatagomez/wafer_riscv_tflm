# WM-811K raw data

Expected file: `LSWMD.pkl`.

Dataset page: https://www.kaggle.com/datasets/qingyi/wm811k-wafer-map

The package inventory and `dataset_provenance.json`, if present, identify the actual dataset included in this handoff. The original data file is preserved without preprocessing or training. No pickle deserialization is needed to download and verify the archive.

Claude must inspect the actual schema and labels, preserve provenance, and implement the train/validation/test protocol in the main prompt. A downloaded dataset does not establish that the model was trained or the RTL was tested.

Keep this large raw file out of ordinary Git commits. Retain the provenance, checksums, and dataset-selection manifests needed to reproduce the experiment.
