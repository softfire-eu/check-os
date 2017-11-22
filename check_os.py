import argparse
import json
import logging.config
import configparser

from keystoneauth1.exceptions import Unauthorized

from sdk.softfire.os_utils import OSClient

log = logging.getLogger(__name__)

def config_script():
    print("Reading image list...")
    config_script = configparser.ConfigParser()
    config_script.read("./list_images.ini")
    image_list = config_script.get('images', 'imagesToCheck')
    image_list = image_list.split(',')
    return image_list


def search_images(testbeds):
    image_list = config_script()
    for testbed_name, testbed in testbeds.items():
        cl = OSClient(testbed_name=testbed_name, testbed=testbed)
        log.info("Checking Testbed %s" % testbed_name)
        log.info("Tenant List:")
        for project in cl.list_tenants():
            try:
                log.info("Checking Project %s" % project.name)
                log.info("Checking project %s" % project.id)
                images = cl.list_images(project.id)
                for img in images:
                    for list in image_list[0:5]:
                        if img.name == list:
                            log.info("Success matched image %s", list)
                        elif img.name != list:
                            log.info("Need to upload image %s", list)
                #log.debug([img.name for img in images])
            except Unauthorized:
                log.warning("Not authorized on project %s" % project.name)

if __name__ == '__main__':
    logging.config.fileConfig("etc/logging.ini", disable_existing_loggers=False)
    parser = argparse.ArgumentParser(description='check Open Stack tenants for softfire')
    parser.add_argument('--os-cred', help='openstack credentials file',
                        default='/etc/softfire/openstack-credentials.json')
    args = parser.parse_args()

    openstack_credentials = args.os_cred #"/etc/softfire/openstack-credentials.json"
    testbeds = {}
    with open(openstack_credentials, "r") as f:
        testbeds = json.loads(f.read())

    search_images(testbeds)
