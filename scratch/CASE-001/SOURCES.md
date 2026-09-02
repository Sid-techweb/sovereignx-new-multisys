# CASE-001 Evidence Manifest & Sources

This manifest details the files compiled for CASE-001 (Pump P-204 anomalous temperature incident) and documents their sources, types, and narrative alignment.

| Filename | Type | Sourcing / Origin | Description |
| --- | --- | --- | --- |
| `pump_P204_SOP.pdf` | PDF (Text) | **Synthetic** | Standard operating thresholds specifying bearing temperature limit (80°C) and vibration limit (4.0 mm/s). |
| `pump_P204_sensor_data.csv` | CSV (Tabular) | **Synthetic** | Five-row sensor time-series documenting normal operations followed by a 91°C bearing temperature and 5.8 mm/s vibration anomaly on 2026-08-12. |
| `pump_P204_inspection_report.pdf` | PDF (Text) | **Synthetic** | Maintenance log detailing visual observation of abnormal vibration, hot bearing housing (91°C), and shutdown recommendation on 2026-08-12. |
| `pump_P204_PID.jpg` | JPG (Image) | **Public Source** | Sourced from TCS Research's Digitize-PID Dataset (`hamzas/digitize-pid-yolo` on HuggingFace), file `DigitizePID_Dataset/images/train/10.jpg`. Relabeled for demo. |
| `pump_P204_photo.jpg` | JPG (Image) | **Public Source** | Sourced from Unsplash (photographer: Lincoln School of Engineering). Plausibly represents Pump P-204 under inspection. |
| `pump_P204_past_incident_report.pdf` | PDF (Text) | **Synthetic** | Historical maintenance file detailing a similar high-temperature (92°C) and high-vibration (5.5 mm/s) failure event on Pump P-204 on 2025-05-18. |
