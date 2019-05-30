#!/bin/bash
# The quota for the projects are cumulative in the versions.
# To check the status of the quotas run this command:
# xfs_quota -xc 'report -hg' /data
# There are 4 options in this script.
# 1. On project create, set a initial quota with groups.
# 2. On version create, set the group of the new version.
# 3. On Quota modification, set the new quota.
# 4. On publish, set the quota of the new group and remove the old one.
if [ $# -eq 1 ]; then
	# This step is forthe creation of a active project
	# Argument #1 is the new group name.
	/usr/sbin/groupadd $1
	/bin/chgrp $1 /data/pn-media/active-projects/$1
	/bin/chmod 2775 /data/pn-media/active-projects/$1
	# The we set the initial quota for the group. 
	/usr/sbin/xfs_quota -xc 'limit -g bsoft=100m bhard=100m '"$1" /data
elif [ $# -eq 2 ]; then
	# This step is for the creation of a versioned project.
	# Argument #1 is the group name. 
	# Argument #2 is the location of the new files.
	/bin/chgrp $1 /data/pn-media/active-projects/$2
	/bin/chmod 2775 $1
elif [ $# -eq 3 ]; then
	# This step is for quota increase or decrease
	# Argument #1 is the group name. 
	# Argument #2 is the location of the new files.
	# Argument #3 is NOT NEEDED
	/usr/sbin/xfs_quota -xc 'limit -g bsoft='"$2"' bhard='"$2"' '"$1" /data
elif [ $# -eq 4 ]; then
	# This step is for the active -> publish phase.
	# Argument #1 is the new group name.
	# Argument #2 is the old group.
	# Argument #3 is the location of the files.
	# Argument #4 is the storage size.
	/usr/sbin/groupadd $1
	/bin/chgrp $1 $3
	/bin/chmod 2775 $3
	# To rename the quota, one removes the quota from the old group, and adds the quota to the new group
	/usr/sbin/xfs_quota -xc 'limit -g bsoft='"$4"' bhard='"$4"' '"$2" /data
	# The we set the initial quota for the group. 
	/usr/sbin/xfs_quota -xc 'limit -g bsoft=0m bhard=0m '"$1" /data
else
	exit 1;
fi
