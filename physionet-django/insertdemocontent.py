# Fill in databases with testing information


from catalog.models import *
from physiobank.models import *
from physiotoolkit.models import *
from physionetworks.models import *
from users.models import User

# Add superuser
User.objects.create_superuser(email="tester@mit.edu", password="Tester1!")

# Add links
Link.objects.create(url="http://physionet.org/physiobank/database/mimic2wdb/", description="MIMIC-III Waveform Database")
#Link.objects.create(url="http://physionet.org/physiobank/database/mimic2wdb/", description="MIMIC-III Waveform Database")


# Add licenses
License.objects.create(name='GPL3', url='https://www.gnu.org/licenses/gpl-3.0.en.html')
License.objects.create(name='MIT', url='https://opensource.org/licenses/MIT')

# Add keywords
Keyword.objects.create(word = "ICU")
Keyword.objects.create(word = "BIDMC")
Keyword.objects.create(word = "LCP")
Keyword.objects.create(word = "Arrhythmia")
Keyword.objects.create(word = "Drug Testing")

# Add contributors
Contributor.objects.create(name='Roger Mark', institution='MIT')
Contributor.objects.create(name='George Moody', institution='MIT')
Contributor.objects.create(name='Ary Goldberger', institution='BIDMC')
Contributor.objects.create(name='Jose Vicente', institution='FDA')

# Add contacts
Contact.objects.create(name='Tom Pollard', email = 'tpollard@mit.edu', institution='MIT')
Contact.objects.create(name='Alistair Johnson', email = 'aewj@mit.edu', institution='MIT')
Contact.objects.create(name='Roger Mark', email = 'rgmark@mit.edu', institution='MIT')
Contact.objects.create(name='George Moody', email = 'george@mit.edu', institution='MIT')
Contact.objects.create(name='Jose Vicente', email = 'jvicente@mit.edu', institution='FDA')


# Add datatypes
DataType.objects.create(name='Waveform', description = 'High resolution regularly sampled data')
DataType.objects.create(name='Clinical', description = 'Detailed patient information')
DataType.objects.create(name='Image', description = 'Visual medical images such as x-rays and MRIs')




# Add databases
mimicoverview = "MIMIC is an openly available dataset developed by the MIT Lab for Computational Physiology, comprising deidentified health data associated with ~40,000 critical care patients. It includes demographics, vital signs, laboratory tests, medications, and more."
mimiccollection = "<p>MIMIC-III is a large, publicly-available database comprising de-identified health-related data associated with approximately sixty thousand admissions of patients who stayed in critical care units of the Beth Israel Deaconess Medical Center between 2001 and 2012. The database includes information such as demographics, vital sign measurements made at the bedside (~1 data point per hour), laboratory test results, procedures, medications, nurse and physician notes, imaging reports, and out-of-hospital mortality. MIMIC supports a diverse range of analytic studies spanning epidemiology, clinical decision-rule improvement, and electronic tool development. It is notable for three factors:</p><ul><li>it is publicly and freely available.</li><li>it encompasses a diverse and very large population of ICU patients.</li><li>it contains high temporal resolution data including lab results, electronic documentation, and bedside monitor trends and waveforms.</li></ul><p>MIMIC-III is an update to MIMIC-II v2.6 and contains the following new classes of data:</p><ul><li>approximately 20,000 additional ICU admissions</li>physician progress notes</li>medication administration records</li><li>more complete demographic information</li><li>current procedural terminology (CPT) codes and Diagnosis-Related Group (DRG) codes</li></ul><p>The MIMIC-III Clinical Database, although de-identified, still contains detailed information regarding the clinical care of patients, and must be treated with appropriate care and respect. Researchers seeking to use the full Clinical Database must formally request access to the MIMIC-III Database.</p>"
mimicfiledescription="<p>MIMIC-III is organized in a relational database with the following tables:</p><ul><li>ADMISSIONS</li><li>CALLOUT</li><li>CAREGIVERS</li><li>CHARTEVENTS</li><li>CPTEVENTS</li><li>D_CPT</li><li>D_ICD_DIAGNOSES</li><li>D_ICD_PROCEDURES</li>        <li>D_ITEMS</li>        <li>D_LABITEMS</li>        <li>DATETIMEEVENTS</li>        <li>DIAGNOSES_ICD</li>        <li>DRGCODES</li>        <li>ICUSTAYS</li>        <li>INPUTEVENTS_CV</li>        <li>INPUTEVENTS_MV</li>        <li>LABEVENTS</li>        <li>MICROBIOLOGYEVENTS</li>        <li>NOTEEVENTS</li>        <li>OUTPUTEVENTS</li><li>PATIENTS</li>        <li>PRESCRIPTIONS</li>        <li>PROCEDUREEVENTS_MV</li>        <li>PROCEDURES_ICD</li><li>SERVICES</li>        <li>TRANSFERS</li></ul>"

db0 = Database(name='MIMIC-III Clinical Database', slug="mimic3cdb", license = License.objects.get(name='MIT'), overview = mimicoverview, publishdate="2009-09-24", collection=mimiccollection, filedescription=mimicfiledescription, DOI='doi:10.19015/KGF8924', isopen=False)
db0.save()
db0.datatypes.add(DataType.objects.get(name="Waveform"), DataType.objects.get(name="Clinical"))
db0.contributors.add(Contributor.objects.get(name="Roger Mark"), Contributor.objects.get(name="Ary Goldberger"))
db0.keywords.add(Keyword.objects.get(word="LCP"), Keyword.objects.get(word="ICU"))
db0.contacts.add(Contact.objects.get(name="Tom Pollard"), Contact.objects.get(name="Alistair Johnson"))
db0.associated_pages.add(Link.objects.get(url="http://physionet.org/physiobank/database/mimic2wdb/"))
#db.associated_files.add()
db0.save()


mitdboverview = "Since 1975, our laboratories at Boston's Beth Israel Hospital (now the Beth Israel Deaconess Medical Center) and at MIT have supported our own research into arrhythmia analysis and related subjects. One of the first major products of that effort was the MIT-BIH Arrhythmia Database, which we completed and began distributing in 1980. The database was the first generally available set of standard test material for evaluation of arrhythmia detectors, and has been used for that purpose as well as for basic research into cardiac dynamics at more than 500 sites worldwide. Originally, we distributed the database on 9-track half-inch digital tape at 800 and 1600 bpi, and on quarter-inch IRIG-format FM analog tape. In August, 1989, we produced a CD-ROM version of the database."
mitdbcollection = "The MIT-BIH Arrhythmia Database contains 48 half-hour excerpts of two-channel ambulatory ECG recordings, obtained from 47 subjects studied by the BIH Arrhythmia Laboratory between 1975 and 1979. Twenty-three recordings were chosen at random from a set of 4000 24-hour ambulatory ECG recordings collected from a mixed population of inpatients (about 60%) and outpatients (about 40%) at Boston's Beth Israel Hospital; the remaining 25 recordings were selected from the same set to include less common but clinically significant arrhythmias that would not be well-represented in a small random sample."
mitdbfiledescription = "This directory contains the entire MIT-BIH Arrhythmia Database. About half (25 of 48 complete records, and reference annotation files for all 48 records) of this database has been freely available here since PhysioNet's inception in September 1999. The 23 remaining signal files, which had been available only on the MIT-BIH Arrhythmia Database CD-ROM, were posted here in February 2005."
db1 = Database(name='MIT-BIH Arrhythmia Database', slug="mitdb", license = License.objects.get(name='MIT'), overview = mitdboverview, publishdate="1999-08-20", collection=mitdbcollection, filedescription=mitdbfiledescription, DOI='doi:10.13026/C2F305')
db1.save()
db1.datatypes.add(DataType.objects.get(name="Waveform"))

db1.contributors.add(Contributor.objects.get(name="Roger Mark"), Contributor.objects.get(name="Ary Goldberger"))
db1.keywords.add(Keyword.objects.get(word="LCP"), Keyword.objects.get(word="ICU"), Keyword.objects.get(word="Arrhythmia"))
db1.contacts.add(Contact.objects.get(name="Roger Mark"), Contact.objects.get(name="George Moody"))
db1.save()


