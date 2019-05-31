#!/bin/bash
# The quota for the projects are cumulative in the versions.
# To check the status of the quotas run this command:
# xfs_quota -xc 'report -hg' /data
# There are 4 options in this script.
# 1. On project create, set a initial quota with groups.
# 2. On version create, set the group of the new version.
# 3. On Quota modification, set the new quota.
# 4. On publish, set the quota of the new group and remove the old one.
if [ $# -eq 2 ]; then
	/usr/sbin/groupadd $1
	/bin/chgrp $1 $2
	/bin/chmod 2775 $2
	# The we set the initial quota for the group. 
	/usr/sbin/xfs_quota -xc 'limit -g bsoft=100m bhard=100m '"$1" /data
elif [ $# -eq 3 ]; then
	# This step is for quota increase or decrease
	if [ "$3" -eq 'modify' ]; then
		# Argument #1 is the group name. 
		# Argument #2 is the new quota size in GB
		# Alter the quota size
		/usr/sbin/xfs_quota -xc 'limit -g bsoft='"$2"' bhard='"$2"' '"$1" /data
	elif [ $3 -eq 'publish' ]; then
		# Rename the group on publish
		/usr/sbin/groupmod -n $1 $2
	elif [ $3 -eq 'delete' ]; then
		# Delete temporary group from version
		/usr/sbin/groupdel $2
	else
		# This step is for the creation of a versioned project.
		# Argument #1 is the group name. 
		# Argument #2 is the group id. 
		# Argument #3 is the location of the new files.
		/usr/sbin/groupadd $1 -g $2 -o
		/bin/chgrp $1 $3
		/bin/chmod 2775 $3
	fi
else
	exit 1;
fi
