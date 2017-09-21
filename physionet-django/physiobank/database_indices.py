import os
import pandas as pd
import wfdb
from physionet.settings import PHYSIOBANK_ROOT
from .models import SignalClass, AnnotationClass, AnnotationLabel, Record, Signal, Annotation, Database




def import_standard_signal_classes():
    for sigclass in wfdb.sigclasses: # Change this to sig_classes later.
        SignalClass.objects.create(name=sigclass.name, description=sigclass.description)

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
        return [str(db.slug) for db in Database.objects.all()]
    return [str(db.slug) for db in Database.objects.all() if str(db.slug) not in exclude_dbs]


# Get all record names from a database
def get_record_names(dbslug):
    dbdir = os.path.join(PHYSIOBANK_ROOT, dbslug)

    recordsfile = os.path.join(dbdir, 'RECORDS')
    if not os.path.isfile(recordsfile):
        print('No WFDB records for database: '+dbslug)
        return None

    with open(recordsfile) as f:
        recordnames = f.readlines()
    recordnames = [r.strip() for r in recordnames]

    return recordnames

def get_annotator_classes(dbslug, log_classes=True):
    """
    Get annotator class information from a database
    Unlogged AnnotatorClass objects will be logged (log_classes=True), or will
    cause the function to raise an exception.

    Returns a list of AnnotatorClass objects
    """
    dbdir = os.path.join(PHYSIOBANK_ROOT, dbslug)
    annotators_file = os.path.join(dbdir, 'ANNOTATORS')

    if not os.path.isfile(annotators_file):
        print('No WFDB annotations for database: '+dbslug)
        return []

    df = pd.read_csv('ANNOTATORS', dtype={'extension':str,'description':str,'human annotated':np.bool})
    
    ann_classes = []
    for i in range(len(df)):
        extension, description, human_annotated = df.loc[i]
        ac = AnnotatorClass.objects.filter(extension=extension, description=description, human_annotated=human_annotated).first() 
        if ac is None:
            if log_classes:
                ac = AnnotatorClass(extension=extension, description=description, human_annotated=human_annotated)
                ac.save()
            else:
                raise Exception('Annotator class has not been logged')
        ann_classes.append(ac)

    return ann_classes





# Try to find a signal class for a signal given its name
def classify_sigclass(signame):
    for sigclass in wfdb.signaltypes:
        if signame.lower() in wfdb.signaltypes[sigclass].signalnames:
            s = SignalClass.objects.get(name=sigclass)
            return s
    
    # Failed to find. Classify as unknown.
    s = SignalClass.objects.get(name='UNKNOWN')
    return s



# ---------- Decorators ----------#


# These 2 are for decorating log_rsa

# Decorator - Apply function for every record in a databaseTrue
def fordb(record_func):
    def func_wrapper(dbslug):
        recordnames = get_record_names(dbslug)
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
    r = Record(name=record.recordname, basefs=record.fs, sig_duration=int(record.siglen/record.fs), database=Database.objects.get(slug=dbslug))
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
def log_annotations(recordname, dbslug, db_ann_classes, logmissingrec=True):
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

            a = Annotation(r, ann_class, labels)
            a.save()
    
    return





def log_rsa(recordname, ann_classes, dbslug):
    """
    Add info about a record, its signals, and its annotations to the relational database.
    ann_classes - a list of AnnotatorClass objects which MUST BE ALREADY LOGGED in the database.
    
    Calling log_record, log_signals, and log_annotations works but contains redundant
    header reading and database queries
    """

    recordpath = os.path.join(PHYSIOBANK_ROOT, dbslug, recordname)
    record = wfdb.rdheader(recordpath)

    r = Record(name=record.recordname, basefs=record.fs, sig_duration=int(record.siglen/record.fs), database=Database.objects.get(slug=dbslug))
    r.save()

    if record.nsig >0:
        for ch in range(record.nsig):
            # Try to get a signalclass
            sigclass = classify_sigclass(record.signame[ch])
            s = Signal(record=r, name=record.signame[ch], signalclass=sigclass, fs=record.fs*record.sampsperframe[ch])
            s.save()

    for ac in ann_classes:
        # Iterating through annotator extensions for the database.
        if os.path.isfile(recordpath+'.'+ac.extension): 
            annotation = wfdb.rdann(recordpath, ac.extension)
            # Already know annotator class. Get annotation label info.
            
            
            a = Annotation()




    if ann_info_df is not None:
        # Iterating through possible annotator extensions
        for i in range(len(ann_info_df)):
            extension, description, human_reviewed =  ann_info_df.loc[i]
            if os.path.isfile(recordpath+'.'+extension):
                ac = None # Work on this...
                annotation = wfdb.rdann(recordpath, extension)
                # Annotation class information

                # 

    return

    record = models.ForeignKey('Record', on_delete=models.CASCADE)
    ann_class = models.ForeignKey('AnnotationClass', related_name='annotation')
    labels = models.ManyToManyField('AnnotationLabel', related_name='annotation', on_delete=models.CASCADE)





# Note: No need for an unlog_r_s function or derivatives. Removing record entries also removes signal entries.

def relog_rsa():
    pass


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