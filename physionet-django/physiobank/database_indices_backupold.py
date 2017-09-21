import os
import wfdb
from physionet.settings import PHYSIOBANK_ROOT
from .models import Signal_Class, Annotation_Class, Annotation_Label, Record, Signal, Annotation, Database




def import_standard_signal_classes():
    for sigclass in wfdb.sig_classes:
        Signal_Class.objects.create(name=sigclass.name, description=sigclass.description)

def import_standard_annotation_classes():
    for annclass in wfdb.ann_classes:
        Annotation_Class.objects.create(extension=annclass.extension, description=annclass.description, human_reviewed=annclass.human_reviewed, standard_wfdb=True)

def import_standard_annotation_labels():
    for annlabel in wfdb.ann_labels:
        Annotation_Label.objects.create(description=annlabel.description)


def get_all_dbslugs(exclude_dbs=None):
    """
    def get_all_dbslugs(exclude_dbs=None):
    List of slug strings for all physiobank databases
    exclude_dbs can be a string or list of string db slugs to exclude
    """
    if type(exclude_dbs) == str:
        exclude_dbs = [exclude_dbs]
    elif exclude_dbs is None:
        return dbslugs = [str(db.slug) for db in Database.objects.all()]
    return [str(db.slug) for db in Database.objects.all() if str(db.slug) not in exclude_dbs]



# Get all record names from a database
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


# Try to find a signal class for a signal given its name
def classify_sigclass(signame):
    for sigclass in wfdb.signaltypes:
        if signame.lower() in wfdb.signaltypes[sigclass].signalnames:
            s = Signal_Class.objects.get(name=sigclass)
            return s
    
    # Failed to find. Classify as unknown.
    s = Signal_Class.objects.get(name='UNKNOWN')
    return s



# ---------- Decorators ----------#

# Decorator - Apply function for every record in a databaseTrue
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
    r = Record(name=record.recordname, basefs=record.fs, sigduration=int(record.siglen/record.fs), database=Database.objects.get(slug=dbslug))
    r.save()
    return

# Remove info about a record from the relational database.
# Note: This automatically removes all signal info linked to the record too (on_delete=models.CASCADE)
def unlog_record(recordname, dbslug):
    Record.objects.filter(name=recordname, database__slug=dbslug).delete()
    return


def log_signals(recordname, dbslug, logmissingrec=True):
    """
    def log_signals(recordname, dbslug, logmissingrec=True):
    Add info about all signals from a record to the relational database
    """
    recordpath = os.path.join(PHYSIOBANK_ROOT, dbslug, recordname)
    record = wfdb.rdheader(recordpath)
    
    if record.nsig == 0:
        return 
    
    r = Record.objects.filter(database=dbslug, name=recordname).first()
    if r is None:
        if logmissingrec is True:
            log_record(recordname, dbslug)
            r = Record.objects.get(database=dbslug, name=recordname)
        else:
            raise Exception('Record '+recordname+' from database '+dbslug+' has not been logged. Cannot log signals.')

    for ch in range(record.nsig):
        # Try to get a signalclass
        sigclass = classify_sigclass(record.signame[ch])
        s = Signal(record=r, name=record.signame[ch], signalclass=sigclass, fs=record.fs*record.sampsperframe[ch])
        s.save()

    return

# Remove info about all signals from a record from the relational database
def unlog_signals(recordname, dbslug):
    Signal.objects.filter(record__name=recordname, record__database__slug=dbslug).delete()
    return

# Add info about all annotation belonging to a record
def log_annotations(recordname, dbslug, db_ann_classes, logmissingrec=True)
    recordpath = os.path.join(PHYSIOBANK_ROOT, dbslug, recordname)

    
    r = Record.objects.filter(database=dbslug, name=recordname).first()
    if r is None:
        if logmissingrec is True:
            log_record(recordname, dbslug)
            r = Record.objects.get(database=dbslug, name=recordname)
        else:
            raise Exception('Record '+recordname+' from database '+dbslug+' has not been logged. Cannot log annotations.')

    for dbac in db_ann_classes:
        if os.path.isfile(recordpath+'.'+dbac):
            annotation = wfdb.rdann(recordpath, dbac)
            # AnnClass
            ac = AnnotationClass.objects.filter(extension=dbac).first()
            if ac is None:
                ac = AnnotationClass(extension=dbac, )
                ac.save()

            # AnnLabels
            annotation_labels = set(annotation.anntype)

            stored_annotation_labels = []
            for label in annotation_labels:
                try:
                    l = AnnotationLabel.objects.get(symbol=label)
                except:
                    l = AnnotationLabel()
                stored_annotation_labels.append(l)

            a = Annotation(record=r, ann_class, labels)
            a.save()
    
    return

    record = models.ForeignKey('Record', on_delete=models.CASCADE)
    ann_class = models.ForeignKey('AnnotationClass', related_name='annotation')
    labels = models.ManyToManyField('AnnotationLabel', related_name='annotation', on_delete=models.CASCADE)




# Add info about a record, its signals, and its annotations to the relational database
def log_rsa(recordname, dbslug):
    # Calling log_record, log_signals, and log_annotations works but contains redundant
    # header reading and database queries

    recordpath = os.path.join(PHYSIOBANK_ROOT, dbslug, recordname)
    record = wfdb.rdheader(recordpath)
    r = Record(name=record.recordname, basefs=record.fs, sigduration=int(record.siglen/record.fs), database=Database.objects.get(slug=dbslug))
    r.save()

    if record.nsig >0:
        for ch in range(record.nsig):
            # Try to get a signalclass
            sigclass = classify_sigclass(record.signame[ch])
            s = Signal(record=r, name=record.signame[ch], signalclass=sigclass, fs=record.fs*record.sampsperframe[ch])
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
def log_db_rsa(recordname, dbslug):
    return log_rsa(recordname, dbslug)

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
def log_all_rsa(dbslug):
    return log_db_r_s(dbslug)

def relog_all_rsa(dbslug):
    unlog_all_records()
    log_all_rsa()
    return