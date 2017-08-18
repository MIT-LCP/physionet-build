import os
import wfdb
from physionet.settings import PHYSIOBANK_ROOT
from .models import WFDB_Record_Info, WFDB_Signal_Info, WFDB_Signal_Type, Database


def get_all_dbslugs():
	"""
	List of slug strings for all physiobank databases
	"""
	return [str(db.slug) for db in Database.objects.all()]

def getrecordnames(dbslug):
	dbdir = os.path.join(PHYSIOBANK_ROOT, dbslug)

	recordsfile = os.path.join(dbdir, 'RECORDS')
	if not os.path.isfile(recordsfile):
		print('No WFDB records for database: '+dbslug)
		return None

	with open(recordsfile) as f:
		recordnames = f.readlines()
	recordnames = [r.strip() for r in recordnames]

	return recordnames


# Try to find a signal class for 
def classify_sigtype(signame):
	for sigtype in wfdb.signaltypes:
		if signame.lower() in wfdb.signaltypes[sigtype].signalnames:
			s = WFDB_Signal_Type.objects.get(name=sigtype)
			return s

	# Failed to find. Classify as unknown.
	s = WFDB_Signal_Type.objects.get(name='UNKNOWN')
	return s



# ---------- Decorators ----------#

# Decorator - Apply function for every record in a database
def fordb(record_func):
	def func_wrapper(dbslug):
		recordnames = getrecordnames(dbslug)
		if recordnames is None:
			return
		for recordname in recordnames:
			record_func(recordname, dbslug)
		return

	return func_wrapper

# Decorator - Apply function for every database
def foralldbs(db_func):
	def func_wrapper():
		dbslugs = get_all_dbslugs()
		for dbslug in dbslugs:
			db_func(dbslug)
		return
	return func_wrapper

# --------------------------------#

# Add info about a record to the relational database
def log_record(recordname, dbslug):
	recordpath = os.path.join(PHYSIOBANK_ROOT, dbslug, recordname)
	record = wfdb.rdheader(recordpath)
	r = WFDB_Record_Info(name=record.recordname, basefs=record.fs, sigduration=int(record.siglen/record.fs), database=Database.objects.get(slug=dbslug))
	r.save()
	return

# Remove info about a record from the relational database.
# Note: This automatically removes all signal info linked to the record too (on_delete=models.CASCADE)
def unlog_record(recordname, dbslug):
	WFDB_Record_Info.objects.filter(name=recordname, database__slug=dbslug).delete()
	return

# Add info about all signals from a record to the relational database
def log_signals(recordname, dbslug, logmissingrec=True):
	recordpath = os.path.join(PHYSIOBANK_ROOT, dbslug, recordname)
	record = wfdb.rdheader(recordpath)
	
	if record.nsig == 0:
		return 
	try:
		r = WFDB_Record_Info.objects.get(database=dbslug, name=recordname)
	except WFDB_Record_Info.DoesNotExist:
		if logmissingrec is True:
			log_record(recordname, dbslug)
			r = WFDB_Record_Info.objects.get(database=dbslug, name=recordname)
		else:
			raise Exception('Record '+recordname+' from database '+dbslug+' has not been logged. Cannot log signals.')

	for ch in range(record.nsig):
		# Try to get a signaltype
		sigtype = classify_sigtype(record.signame[ch])
		s = WFDB_Signal_Info(record=r, name=record.signame[ch], signaltype=sigtype, fs=record.fs*record.sampsperframe[ch])
		s.save()

	return

# Remove info about all signals from a record from the relational database
def unlog_signals(recordname, dbslug):
	WFDB_Signal_Info.objects.filter(record__name=recordname, record__database__slug=dbslug).delete()
	return

# Add info about a record and its signals to the relational database
def log_r_s(recordname, dbslug):
	# Calling log_record and log_signals works but contains redundant
	# header reading and database queries

	recordpath = os.path.join(PHYSIOBANK_ROOT, dbslug, recordname)
	record = wfdb.rdheader(recordpath)
	r = WFDB_Record_Info(name=record.recordname, basefs=record.fs, sigduration=int(record.siglen/record.fs), database=Database.objects.get(slug=dbslug))
	r.save()

	if record.nsig == 0:
		return 

	for ch in range(record.nsig):
		# Try to get a signaltype
		sigtype = classify_sigtype(record.signame[ch])
		s = WFDB_Signal_Info(record=r, name=record.signame[ch], signaltype=sigtype, fs=record.fs*record.sampsperframe[ch])
		s.save()

	return

# Note: No need for an unlog_r_s function or derivatives. Removing record entries also removes signal entries.


# Add info about all records in a database to the relational database
@fordb
def log_db_records(recordname, dbslug):
	return log_record(recordname, dbslug)

# Remove info about all records (and their signals) in a database from the relational database
@fordb
def unlog_db_records(recordname, dbslug):
	return unlog_record(recordname, dbslug)

# Add info about all records in a database to the relational database
@fordb
def log_db_signals(recordname, dbslug):
	return log_signals(recordname, dbslug)

# Remove info about all signals from all records in a database from the relational database
@fordb
def unlog_db_signals(recordname, dbslug):
	return unlog_signals(recordname, dbslug)

# Add info about all records in a database to the relational database
@fordb
def log_db_r_s(recordname, dbslug):
	return log_r_s(recordname, dbslug)


# Add info about all records in every database to the relational database
@foralldbs
def log_all_records(dbslug):
	return log_db_records(dbslug)

# Remove info about all records in every database from the relational database
@foralldbs
def unlog_all_records(dbslug):
	return unlog_db_records(dbslug)

@foralldbs
def log_all_signals(dbslug):
	return log_db_signals(dbslug)

# Remove info about all records in every database from the relational database
@foralldbs
def unlog_all_signals(dbslug):
	return unlog_db_signals(dbslug)

@foralldbs
def log_all_r_s(dbslug):
	return log_db_r_s(dbslug)

def relog_all_r_s(dbslug):
	unlog_all_records()
	log_all_r_s()
	return