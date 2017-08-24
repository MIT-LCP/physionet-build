# Fill in databases with testing information


from catalog.models import *
from physiobank.models import *
from physiobank.database_indices import *
from physiobank.database_indices import log_all_r_s
from physiotoolkit.models import *
from physionetworks.models import *
from users.models import User
from physionet.settings import PHYSIOBANK_ROOT
from catalog.utility import get_dir_size
import os
import wfdb

# Add superuser
User.objects.create_superuser(email="tester@mit.edu", password="Tester1!")

# Add links
Link.objects.create(url="http://physionet.org/physiobank/database/mimic2wdb/", description="MIMIC-III Waveform Database")
#Link.objects.create(url="http://physionet.org/physiobank/database/mimic2wdb/", description="MIMIC-III Waveform Database")


# Add licenses
License.objects.create(name='GPL3', url='https://www.gnu.org/licenses/gpl-3.0.en.html')
License.objects.create(name='MIT', url='https://opensource.org/licenses/MIT')

# Add keywords
Keyword.objects.create(word = "ECG")
Keyword.objects.create(word = "ICU")
Keyword.objects.create(word = "BIDMC")
Keyword.objects.create(word = "LCP")
Keyword.objects.create(word = "Arrhythmia")
Keyword.objects.create(word = "PTCA")
Keyword.objects.create(word = "ABP")


# Add contributors
Contributor.objects.create(name='Roger Mark', institution='MIT')
Contributor.objects.create(name='George Moody', institution='MIT')
Contributor.objects.create(name='Ary Goldberger', institution='BIDMC')
Contributor.objects.create(name='Pablo Laguna', institution='Zaragoza University')
Contributor.objects.create(name='Jeffrey Cooper', institution='MGH')

# Add contacts
Contact.objects.create(name='Tom Pollard', email = 'tpollard@mit.edu', institution='MIT')
Contact.objects.create(name='Alistair Johnson', email = 'aewj@mit.edu', institution='MIT')
Contact.objects.create(name='Roger Mark', email = 'rgmark@mit.edu', institution='MIT')
Contact.objects.create(name='George Moody', email = 'george@mit.edu', institution='MIT')
Contact.objects.create(name='Pablo Laguna', email = 'laguna@unizar.es', institution='Zaragoza University')
Contact.objects.create(name='Jeffrey Cooper', email = 'jc@mgh.edu', institution='MGH')

# Add datatypes
DataType.objects.create(name='Waveform', description = 'High resolution regularly sampled data')
DataType.objects.create(name='Clinical', description = 'Detailed patient information')
DataType.objects.create(name='Image', description = 'Visual medical images such as x-rays and MRIs')

# Add signal types
import_signal_classes()
# Add annotation types
import_annotation_classes()
# Add annotation labels
import_annotation_labels()


# Add databases
mimicoverview = "MIMIC is an openly available dataset developed by the MIT Lab for Computational Physiology, comprising deidentified health data associated with ~40,000 critical care patients. It includes demographics, vital signs, laboratory tests, medications, and more."
mimiccollection = "<p>MIMIC-III is a large, publicly-available database comprising de-identified health-related data associated with approximately sixty thousand admissions of patients who stayed in critical care units of the Beth Israel Deaconess Medical Center between 2001 and 2012. The database includes information such as demographics, vital sign measurements made at the bedside (~1 data point per hour), laboratory test results, procedures, medications, nurse and physician notes, imaging reports, and out-of-hospital mortality. MIMIC supports a diverse range of analytic studies spanning epidemiology, clinical decision-rule improvement, and electronic tool development. It is notable for three factors:</p><ul><li>it is publicly and freely available.</li><li>it encompasses a diverse and very large population of ICU patients.</li><li>it contains high temporal resolution data including lab results, electronic documentation, and bedside monitor trends and waveforms.</li></ul><p>MIMIC-III is an update to MIMIC-II v2.6 and contains the following new classes of data:</p><ul><li>approximately 20,000 additional ICU admissions</li>physician progress notes</li>medication administration records</li><li>more complete demographic information</li><li>current procedural terminology (CPT) codes and Diagnosis-Related Group (DRG) codes</li></ul><p>The MIMIC-III Clinical Database, although de-identified, still contains detailed information regarding the clinical care of patients, and must be treated with appropriate care and respect. Researchers seeking to use the full Clinical Database must formally request access to the MIMIC-III Database.</p>"
mimicfiledescription="<p>MIMIC-III is organized in a relational database with the following tables:</p><ul><li>ADMISSIONS</li><li>CALLOUT</li><li>CAREGIVERS</li><li>CHARTEVENTS</li><li>CPTEVENTS</li><li>D_CPT</li><li>D_ICD_DIAGNOSES</li><li>D_ICD_PROCEDURES</li>        <li>D_ITEMS</li>        <li>D_LABITEMS</li>        <li>DATETIMEEVENTS</li>        <li>DIAGNOSES_ICD</li>        <li>DRGCODES</li>        <li>ICUSTAYS</li>        <li>INPUTEVENTS_CV</li>        <li>INPUTEVENTS_MV</li>        <li>LABEVENTS</li>        <li>MICROBIOLOGYEVENTS</li>        <li>NOTEEVENTS</li>        <li>OUTPUTEVENTS</li><li>PATIENTS</li>        <li>PRESCRIPTIONS</li>        <li>PROCEDUREEVENTS_MV</li>        <li>PROCEDURES_ICD</li><li>SERVICES</li>        <li>TRANSFERS</li></ul>"
db0 = Database(name='MIMIC-III Clinical Database', slug="mimic3cdb", license = License.objects.get(name='MIT'), overview = mimicoverview, publishdate="2009-09-24", collection=mimiccollection, filedescription=mimicfiledescription, DOI='doi:10.19015/KGF8924', isopen=False, size=get_dir_size(os.path.join(PHYSIOBANK_ROOT, 'mimimc3cdb')))
db0.save()
db0.datatypes.add(DataType.objects.get(name="Waveform"), DataType.objects.get(name="Clinical"))
db0.contributors.add(Contributor.objects.get(name="Roger Mark"), Contributor.objects.get(name="Ary Goldberger"))
db0.keywords.add(Keyword.objects.get(word="LCP"), Keyword.objects.get(word="ICU"))
db0.contacts.add(Contact.objects.get(name="Tom Pollard"), Contact.objects.get(name="Alistair Johnson"))
db0.associated_pages.add(Link.objects.get(url="http://physionet.org/physiobank/database/mimic2wdb/"))
db0.save()

mitdboverview = "Since 1975, our laboratories at Boston's Beth Israel Hospital (now the Beth Israel Deaconess Medical Center) and at MIT have supported our own research into arrhythmia analysis and related subjects. One of the first major products of that effort was the MIT-BIH Arrhythmia Database, which we completed and began distributing in 1980. The database was the first generally available set of standard test material for evaluation of arrhythmia detectors, and has been used for that purpose as well as for basic research into cardiac dynamics at more than 500 sites worldwide. Originally, we distributed the database on 9-track half-inch digital tape at 800 and 1600 bpi, and on quarter-inch IRIG-format FM analog tape. In August, 1989, we produced a CD-ROM version of the database."
mitdbcollection = "The MIT-BIH Arrhythmia Database contains 48 half-hour excerpts of two-channel ambulatory ECG recordings, obtained from 47 subjects studied by the BIH Arrhythmia Laboratory between 1975 and 1979. Twenty-three recordings were chosen at random from a set of 4000 24-hour ambulatory ECG recordings collected from a mixed population of inpatients (about 60%) and outpatients (about 40%) at Boston's Beth Israel Hospital; the remaining 25 recordings were selected from the same set to include less common but clinically significant arrhythmias that would not be well-represented in a small random sample."
mitdbfiledescription = "This directory contains the entire MIT-BIH Arrhythmia Database. About half (25 of 48 complete records, and reference annotation files for all 48 records) of this database has been freely available here since PhysioNet's inception in September 1999. The 23 remaining signal files, which had been available only on the MIT-BIH Arrhythmia Database CD-ROM, were posted here in February 2005."
db1 = Database(name='MIT-BIH Arrhythmia Database', slug="mitdb", license = License.objects.get(name='MIT'), overview = mitdboverview, publishdate="1999-08-20", collection=mitdbcollection, filedescription=mitdbfiledescription, DOI='doi:10.13026/C2F305', size=get_dir_size(os.path.join(PHYSIOBANK_ROOT, 'mitdb')))
db1.save()
db1.datatypes.add(DataType.objects.get(name="Waveform"))
db1.contributors.add(Contributor.objects.get(name="Roger Mark"), Contributor.objects.get(name="Ary Goldberger"))
db1.keywords.add(Keyword.objects.get(word="LCP"), Keyword.objects.get(word="ICU"), Keyword.objects.get(word="Arrhythmia"))
db1.contacts.add(Contact.objects.get(name="Roger Mark"), Contact.objects.get(name="George Moody"))
db1.save()

staffiiioverview = "The STAFF III database was acquired during 1995–96 at Charleston Area Medical Center (WV, USA) where single prolonged balloon inflation had been introduced to achieve optimal results of percutaneous transluminal coronary angiography (PTCA) procedures, replacing the typical series of brief inflations. The lead investigator Dr. Stafford Warren designed the study protocol together with Dr. Galen Wagner at Duke University Medical Center (Durham, NC, USA); Dr. Michael Ringborn (Blekinge Hospital, Karlskrona, Sweden) was responsible for data acquisition. The database consists of ECG recordings from 104 patients, accounting for substantial inter-patient variability in reaction to prolonged balloon inflation as well as variability of heart rhythm and waveform morphology. Only patients receiving elective PTCA in one of the major coronary arteries were included. Patients suffering from ventricular tachycardia, undergoing an emergency procedure, or demonstrating signal loss during acquisition, were excluded."
staffiiicollection = "The standard procedure was defined as follows. Pre-inflation (baseline) ECGs were acquired for 5 min at rest in supine position in either a relaxing room or the catheterization laboratory, or both, prior to any catheter insertion. Inflation ECGs were acquired up to five times in each patient. The mean inflation time was 4 min 23 s, ranging from 1 min 30 s to 9 min and 54 s. In 86 inflations, the balloon did not go up immediately at the beginning of the recording, but after 4 to 205 s into the recording. Moreover, in some cases, the balloon went down before the recording ended, with a postinflation period >60 s in all but 11 inflations. All time instants related to balloon inflation/deflation were manually annotated. Post-inflation ECGs were acquired for 5 min at rest in supine position in either the catheterization laboratory or the relaxing room, or both. The database contains a total of 152 occlusions in the major coronary arteries, distributed as 58 occlusions in left anterior descendent (LAD) artery, 59 in right coronary artery (RCA), 32 in left circumflex artery (LCX), and 3 in the left main (LM) artery. Based on ECG criteria, 35 patients had previous myocardial infarction. The database consists of standard 12-lead ECG data. Standard electrode placements were used for the precordial ECG leads, whereas the limb leads were obtained with the Mason–Likar electrode configuration to reduce noise originating from skeletal muscle. Data acquisition was based on custom-made equipment by Siemens–Elema AB (Solna, Sweden) with an extraordinary dynamic input amplitude range. The ECG was digitized at a sampling rate of 1000 Hz and an amplitude resolution of 0.625 µV. These specifications ensured that high-resolution digital signals could be produced which made it possible to analyze high-frequency components as well as other subtle electrophysiological phenomena.Originally, scntigraphic images were also obtained by injecting Technetium Tc99m Sestamibi for localizing the myocardium supplied by the temporarily occluded artery. However, these images have not come to play any significant role as they are only available for a small number of all patients, and therefore not provided for download on the PhysioNet website. Injections during catheterization and angiography may case changes of the ECG morphology, and the injections are therefore annotated. However, not all injections were annotated, and therefore users are advised to be cautious when ECG changes are observed that mimic the dynamics commonly observed together with annotated injections."
staffiiifiledescription = "All clinical information and annotations are included in the xlsx and ods format spreadsheets, including columns which describe the measurement type correspond to each recording file. The event times related to the balloon inflation/deflation and the contrast injection are also provided as WFDB annotator files. Each recording in the database is defined by the data files *.dat and *.hea, together with an annotation file *.event which states times for balloon inflation/deflation and contrast injection (only available for certain recordings)."
db2 = Database(name='STAFF-III Database', slug="staffiii", license = License.objects.get(name='MIT'), overview = staffiiioverview, publishdate="2017-01-22", collection=staffiiicollection, filedescription=staffiiifiledescription, DOI='doi:10.13526/C2G329', size=get_dir_size(os.path.join(PHYSIOBANK_ROOT, 'staffiii')))
db2.save()
db2.datatypes.add(DataType.objects.get(name="Waveform"))
db2.contributors.add(Contributor.objects.get(name="Pablo Laguna"))
db2.keywords.add(Keyword.objects.get(word="PTCA"), Keyword.objects.get(word="ECG"))
db2.contacts.add(Contact.objects.get(name="Pablo Laguna"))
db2.save()

mghdboverview = "The Massachusetts General Hospital/Marquette Foundation (MGH/MF) Waveform Database is a comprehensive collection of electronic recordings of hemodynamic and electrocardiographic waveforms of stable and unstable patients in critical care units, operating rooms, and cardiac catheterization laboratories. It is the result of a collaboration between physicians, biomedical engineers and nurses at the Massachusetts General Hospital. The database consists of recordings from 250 patients and represents a broad spectrum of physiologic and pathophysiologic states. Individual recordings vary in length from 12 to 86 minutes, and in most cases are about an hour long."
mghdbcollection = " The typical recording includes three ECG leads, arterial pressure, pulmonary arterial pressure, central venous pressure, respiratory impedance, and airway CO2 waveforms. Some recordings include intra-cranial, left atrial, ventricular and/or intra-aortic-balloon pressure waveforms. ECG calibration, pressure zero, pressure calibration, and pressure/catheter frequency response tests are also recorded. Relevant clinical data and events are documented for each file.The original signals were recorded on 8-channel instrumentation tape and then digitized at twice real time using sample(1). The raw sampling rate of 1440 samples per second per signal was reduced by a factor of two to yield an effective rate of 360 samples per second per signal relative to real time. This approach permitted the use of low-order analog antialiasing in combination with high-order digital FIR antialiasing to minimize phase distortion in the digitized signals (see sample8.hea for the FIR coefficients)."
mghdbfiledescription = "Each record includes an annotation (.ari) file, which contains beat and event labels. The annotation files have been made available in their present form to aid users of the database in locating interesting features of the recordings. The current annotation files, although they have been prepared with care and substantial effort, are likely to contain a small number of errors."
db3 = Database(name='MGH Database', slug="mghdb", license = License.objects.get(name='MIT'), overview = mghdboverview, publishdate="1992-05-01", collection=mghdbcollection, filedescription=mghdbfiledescription, DOI='doi:10.53531/C2V628', size=get_dir_size(os.path.join(PHYSIOBANK_ROOT, 'mghdb')))
db3.save()
db3.datatypes.add(DataType.objects.get(name="Waveform"))
db3.contributors.add(Contributor.objects.get(name="Jeffrey Cooper"))
db3.keywords.add(Keyword.objects.get(word="ABP"), Keyword.objects.get(word="ECG"))
db3.contacts.add(Contact.objects.get(name="Jeffrey Cooper"))
db3.save()


# Add record and signal info
log_all_r_s()




