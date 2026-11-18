# Pregnancy as a Diagnostic Catch-up Window in U.S. Health Claims

Joseph Bommarito, Elizabeth Anderson, Lilly Springer, Yurong Zhang, and Misty Heggeness

This study examines whether pregnancy creates more opportunities for existing health conditions to enter the medical record. Using matched U.S. claims records, it compares outpatient contact and first recorded diagnoses around pregnancy onset. It also examines differences by insurance payer and tracks repeat diagnosis records after delivery.

## Replication materials

| File or folder | Contents |
| --- | --- |
| [Aggregate data](S1_Data/README.txt) | Estimates, counts, and data definitions underlying the exhibits |
| [Analysis and figure code](S1_Code/README.txt) | Analysis scripts, figure scripts, and instructions for both workflows |

## Reproduce the figures

Clone or download the repository and open `working-papers/pregnancy-diagnostic-catch-up/`. Run the following from the paper folder using Python 3.12 with Arial available to Matplotlib.

```sh
python -m pip install -r S1_Code/requirements_plot.txt
python S1_Code/reproduce_figures.py --output reproduced_figures
```

The script reads the included aggregates and writes PNG and 600 dpi TIFF copies of all three figures. See [the validation record](S1_Code/VALIDATION.txt) for the original reproduction checks.

## Rerun the analysis

The analysis scripts require the prepared databases and procedure file described in the input guide. The study used de-identified claims licensed from HealthVerity. Recreating the analytical databases from raw claims requires separate source data and processing. [Analysis input guide](S1_Code/INPUTS.txt) · [HealthVerity access inquiries](https://healthverity.com/healthverity-marketplace-request/)
