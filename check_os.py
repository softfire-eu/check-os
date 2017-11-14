import argparse
import json
import logging.config

from sdk.softfire.os_utils import OSClient

log = logging.getLogger(__name__)

if __name__ == '__main__':
    logging.config.fileConfig("etc/logging.ini", disable_existing_loggers=False)
    parser = argparse.ArgumentParser(description='check Open Stack tenants for softfire')
    parser.add_argument('--os-cred', help='openstack credentials file',
                        default='/etc/softfire/openstack-credentials.json')
    args = parser.parse_args()

    openstack_credentials = args.os_cred
    testbeds = {}
    with open(openstack_credentials, "r") as f:
        testbeds = json.loads(f.read())

    for testbed_name, testbed in testbeds.items():
        cl = OSClient(testbed_name=testbed_name, testbed=testbed)
        log.info("Checking Testbed %s" % testbed_name)
        for project in cl.list_tenants():
            log.info("Checking Project %s" % project.name)
