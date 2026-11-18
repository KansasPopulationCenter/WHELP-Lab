S1 Data. Aggregate data for the two manuscript tables and three figures

This folder contains aggregate data only. It contains no individual records,
patient identifiers, patient-level dates, claims, or licensed source databases.
It is a machine-readable companion to the existing manuscript tables and figures;
it does not introduce additional supplementary result tables.

From the paper folder, see S1_Code/README.txt for instructions for
reproducing the figures and for information about the licensed input data.

Contents and mapping
--------------------
Table 1: tables/Table1.csv is a verbatim cell-text extraction of the first table.
  Table1_underlying_estimates.csv provides its unrounded aggregate counts,
  denominators, rates, paired differences and confidence limits.
  primary/ahn_results.json contains the same primary estimates and weekly data.
Table 2: tables/Table2.csv is a verbatim cell-text extraction of the second table.
  payer/outpatient_contact.csv provides the original unrounded stratum estimates.
  payer/contact_payer_contrast.csv provides the Medicaid-minus-commercial contrast.
  Table2.csv repeats merged Word cells and preserves both header rows; repeated
  values are the same merged estimate, not separate estimates or observations.
Figure 1: primary/ahn_results.json and primary/ahn_procedures.json.
Figure 2: payer/outpatient_contact_timing.csv and payer/diagnosis_timing.csv.
Figure 3A: followup/first_year.csv (six rows).
Figure 3B: followup/beyond_first_year_min90.csv (six rows).

Primary analysis population
---------------------------
The primary WH_Ahn analysis contains 175,505 matched pairs. These are not data
from the separate, earlier claims extract. The included JSON files are selected
aggregate fields from the original analysis outputs, without changes to values.
Only the shared-code condition definitions used in Table 1/Figure 1 are included.

Interpretation
--------------
Diagnosis codes record documentation, not necessarily a previously unknown
condition. Payer strata in Table 2 and Figure 2 use the pregnancy-group woman's
payer at delivery discharge; each original matched comparison remains paired.
Figure 3 contains pregnancy-group women only and has different eligible samples
and observation periods in its two panels. The manuscript captions and methods
describe these distinctions; DATA_DICTIONARY.txt summarizes the field definitions.

Provenance
----------
MANIFEST.csv maps each file to its original analysis or manuscript source and
records SHA-256 checksums and any selection/reformatting. Source names are project
relative; private local directory prefixes have not been distributed.
