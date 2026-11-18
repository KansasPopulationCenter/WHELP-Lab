S1 Code. Analysis and figure code

Scope and reproducibility status
--------------------------------
This folder contains (1) an executable reproduction of all three final figures
from public aggregate data in S1_Data, and (2) the original custom licensed-data
analysis logic with portable file-path configuration. No data analysis has been
rerun to prepare this submission package. The figure reproduction was run and
its TIFF pixels, size, resolution, mode, and compression checked against the
submission figures. See VALIDATION.txt for the final result.

The licensed-data scripts begin from two PREPARED DuckDB databases and a procedure
file described in INPUTS.txt. They do not build those databases from raw vendor
claims. Upstream construction code and the licensed inputs are not in this
archive. This is therefore NOT a tested end-to-end reproduction from a raw
claims release. Access to equivalent prepared inputs is needed to rerun the
clinical analyses; the corresponding author should specify lawful data-access
arrangements in the manuscript data-availability statement. No public access
right to the licensed patient-level source data is asserted by this archive.

Reproduce the submitted figures (no licensed data required)
---------------------------------------------------------
1. From the pregnancy-diagnostic-catch-up folder, where S1_Data and S1_Code
   are siblings, install the plotting packages using Python 3.12:
     python -m pip install -r S1_Code/requirements_plot.txt
2. Make the Arial font available to matplotlib. Arial is not distributed here.
   The scripts intentionally require this font; substituting another font can
   change the publication layout. The scripts require no internet connection.
3. Run:
     python S1_Code/reproduce_figures.py --output reproduced_figures
   Optional: --data /path/to/S1_Data
4. Outputs are Fig1.png/Fig1.tif, Fig2.png/Fig2.tif and Fig3.png/Fig3.tif plus
   JSON validation reports. TIFFs are 600 dpi, RGB, LZW-compressed. They contain
   panel labels and keys; full captions belong in the manuscript.

The plotting package versions in requirements_plot.txt reproduce the submission
environment. Figure pixels may vary across font versions/platforms. Data and
statistical assertions embedded in the scripts must still pass. Only aggregate
data are read by this command; no working patient database is created.

Rerun the custom analyses with licensed prepared inputs
------------------------------------------------------
Use a separate environment with requirements_analysis.txt installed. DuckDB
1.5.5 is the recorded original analysis version; its hashing is used in matching,
so changing this version may change the selected matched sample.

  python -m pip install -r S1_Code/requirements_analysis.txt
  python S1_Code/run_licensed_analysis.py --source-root /local/WH_Ahn     --work /private/work --output /local/aggregate_outputs

The single command above is shown over two lines for readability; on Windows,
enter it on one line. It runs these original analyses in order:
  1. analyze_ahn.py: matched primary cohort and diagnosis-history/time analyses.
  2. analyze_ahn_contacts.py: procedure-derived billed evaluation-day measures.
  3. analyze_payer_at_delivery.py: payer stratification, pair-level uncertainty,
     heterogeneity and the original validation/sensitivity calculations.
  4. analyze_year_followup.py: builds the early-first cohorts and first-year
     eligible sample. The original script also calculates months 7-12; that
     endpoint is not included in the submitted figure or S1_Data.
  5. analyze_beyond_year_min90.py: recalculates available follow-up after the
     first discharge anniversary, requiring >90 available days and continuous
     enrollment through 31 December 2024.

The wrapper configures WH_AHN_ROOT and copies the original protocol JSON files
to the names expected by the analyses. Individual scripts can also be run with
WH_AHN_ROOT set and the same arguments, following this order. Analysis scripts
create a private ahn_work.duckdb containing patient-level intermediate records.
Do not distribute the private work directory. They use 6-8 GB configured memory
and scan the procedure file; sufficient local time and disk space are required.

The original scripts include assertions for 175,505 matched pairs, non-reuse of
patients, early-first cohort sizes, pooled aggregate reconciliation, window
boundaries, coverage and follow-up counts. Assertions intentionally fail if the
prepared source release differs from the analyzed release. No attempt should
be made to bypass these assertions merely to reproduce target numbers.

The unrestricted six-row beyond-year file in reference_data is retained solely
because the original restricted analysis compares its preliminary aggregate
counts to that verification reference. It is not an additional supplementary
result table and is not used in the submitted figure. Changing that reference
does not supply the patient-level data needed to rerun the analysis.

What was changed for this archive
--------------------------------
The statistical code and selection logic were retained. Only private/local
source-root paths, output defaults, dependency-folder injection, and the
validation-reference path were configured for portability. Plot scripts use
S1_Data and an explicit output folder; private manuscript-image comparisons and
400-dpi QA exports were removed. The wrappers/documentation are new. MANIFEST.csv
records each source file, source hash, packaged hash and change classification.
The code was parsed for syntax, and the aggregate figure path was executed.
The licensed-data path was NOT executed or independently revalidated for this
submission package. The upstream prepared-database boundary remains a material
limitation to independent reproduction from raw claims.

Table data
----------
The two manuscript tables are supplied as verbatim aggregate CSV cell text and
unrounded supporting estimates in S1_Data. This archive does not reformat or
edit the Word document. Table 2 merged cells repeat in its rectangular CSV.
