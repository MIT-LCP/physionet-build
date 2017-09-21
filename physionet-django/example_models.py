





class BaseProject():
    publishdate = models.DateField()

    owners = models.ManyToManyField(Owner)

    DOI = models.ForeignKey(DOI)

    is_open = models.BooleanField()





# The work in progress
class Project(BaseProject):

    creationdate = models.DataField()

    useraccountemail = models.ForeignKey(user)

    collaborators = models.ManyToManyField(user)


    # active, pending, rejected, 
    status = models.SmallIntegerField()







class Database(BaseProject):

    originproject = ForeignKey(Project)





class Software(BaseProject):


    originproject = ForeignKey(Project)

    software_types = Model











































DataPapers()






class BigProject():

    # datacite
    identifier
    creators
    titles # the title of this project
    publisher
    publicationyear
    resourecetype
    subjects
    contributors
    dates
    language
    alternativeidentifiers
    relatedidentifiers
    sizes
    formats
    version
    rightslist
    descriptions
    geolocations
    fundingreferences
    awardnumber
    awardtitle










