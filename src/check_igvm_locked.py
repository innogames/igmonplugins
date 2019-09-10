from adminapi.dataset import Query
from adminapi.dataset.filters import Not, Any
from datetime import datetime, timezone, timedelta
from subprocess import Popen, PIPE, DEVNULL

import argparse




def main():

    parser = argparse.ArgumentParser(description='nagios check for long running igvm_locked attribute')
    parser.add_argument("monitoring_master", type=str)
    parser.add_argument("--time_in_minutes", type=int, default=480)
    args = parser.parse_args()

    max_minutes = args.time_in_minutes
    master = args.monitoring_master

    hosts = Query({'servertype': Any('hypervisor', 'vm'), 'no_monitoring': False, 'state': Not('retired'), 'hostname': 'luiz.test.ig.local'}, ['igvm_locked', 'hostname'])

    hosts_not_locked = []
    hosts_locked = []
    for host in hosts:
        if not host['igvm_locked']:
            hosts_not_locked.append(host)
        elif (datetime.now(timezone.utc) - host['igvm_locked']) > timedelta(minutes=max_minutes):
            hosts_locked.append(host)
        else:
            hosts_not_locked.append(host)

    console_out(hosts_locked, max_minutes)
    nsca_out = nagios_create(hosts_locked, hosts_not_locked, max_minutes)
    nagios_send(master, nsca_out)

def nagios_create(hosts_locked, hosts_not_locked, max_minutes):
    nsca_output = ""
    for host in hosts_locked:
        nsca_output += ('{}\tigvm_locked\t{}\tWARNING - IGVM-locked longer than {}h {}m\x17'
            .format(host['hostname'],1,int(max_minutes/60),int(max_minutes - 60 * (max_minutes/60))))

    for host in hosts_not_locked:
        nsca_output += ('{}\tigvm_locked\t{}\tOK\x17'
            .format(host['hostname'],0))

    return(nsca_output)

def nagios_send(host, nsca_output):
    result = True
    nsca = Popen(
        [
            '/usr/sbin/send_nsca',
            '-H', host,
            '-c', '/etc/send_nsca.cfg',
        ],
        stdin=PIPE,
        stdout=DEVNULL,
        stderr=DEVNULL
    )
    nsca.communicate(nsca_output.encode())
    returncode = nsca.wait()
    if returncode > 0:
        result = False

    return result


def console_out(hosts_locked, max_minutes):
    count_locked_servers = 0
    locked_hosts = ""
    for host in hosts_locked:
        #locked_hosts = str(locked_hosts) + str(host['hostname'] + ":" + str(host['igvm_locked']) + "\n")
        locked_hosts += "{}:{}\n".format(host['hostname'], host['igvm_locked'])
        count_locked_servers += 1

    if locked_hosts == "":
       print("No igvm_locked Servers !!!")
    else:
       #print("This servers are locked longer than " + str(int(max_minutes/60)) + "h and " + str(max_minutes - (int(max_minutes/60) * 60)) + "m :" + str(locked_hosts))
        hours = int(max_minutes/60)
        minutes = max_minutes - (int(max_minutes/60) * 60)



        print("({}) server/s are/is locked longer than {}h and {}m : \n{}".format(count_locked_servers, hours, minutes, locked_hosts))





if __name__ == '__main__':
    main()


