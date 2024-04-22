Server migration checklist
==========================

[ ] **Target**: Check network (reachable, link speed)
[ ] **Target**: Check disk (enough space, no RAID problems)
[ ] **Target**: Pre-synchronize files
[ ] **DNS**: Set minimum TTL
[ ] **Target**: Check/upgrade system packages
[ ] **Target**: Update `/physionet/physionet-build.git`
[ ] **Target**: Update `/physionet/.env`
[ ] **Target**: Update system config files
[ ] **Target**: Enable `SYSTEM_MAINTENANCE_NO_CHANGES`
[ ] **Source**: Dump and transfer database
[ ] **Target**: Restore database (reload uwsgi)
[ ] **Target**: Test nginx/uwsgi is working
[ ] **Target**: Update `/etc/aliases`
[ ] **Target**: Update certificates
[ ] **Target**: Test postfix is working
[ ] **Target**: Test haproxy is working
[ ] **Target**: Configure iptables
[ ] **Target**: Configure qdisc

[ ] (proxy-backward) **Target**: Redirect connections to haproxy
[ ] (proxy-backward) **DNS**: Update records

[ ] **Target**: Stop background-tasks daemon
[ ] **Source**: Stop background-tasks daemon
[ ] **Source**: Enable `SYSTEM_MAINTENANCE_NO_UPLOAD` (reload uwsgi)
[ ] **Target**: Synchronize files
[ ] **Source**: Enable `SYSTEM_MAINTENANCE_NO_CHANGES` (reload uwsgi)
[ ] **Source**: Dump and transfer database
[ ] **Target**: Restore database (reload uwsgi)
[ ] **Target**: Check new content is visible

[ ] (proxy-forward) **Source**: Redirect connections to haproxy
[ ] (proxy-forward) **DNS**: Update records

[ ] **Target**: Disable `SYSTEM_MAINTENANCE_NO_CHANGES` (reload uwsgi)
[ ] **Target**: Remove iptables redirections
[ ] **Target**: Start background-tasks daemon
[ ] **DNS**: Set normal TTL
