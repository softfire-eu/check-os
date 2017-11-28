import argparse
import json
import logging.config
import configparser

from keystoneauth1.exceptions import Unauthorized

from sdk.softfire.os_utils import OSClient

log = logging.getLogger(__name__)

def image_list():
    file_path = '/net/u/dsa/Projects/Softfire/check-os/etc/images_list.json'
    image_names = []
    paths = []
    with open(file_path, "r") as f:
        images = json.loads(f.read())
    for key, val in images.items():
        # print(val)
        for i in val:
            image_names.append(i.get('name'))
            paths.append(i.get('path'))
    return image_names, paths


def search_images(testbeds):
    image_names, path = image_list()
    for testbed_name, testbed in testbeds.items():
        cl = OSClient(testbed_name=testbed_name, testbed=testbed)
        log.info("Checking Testbed %s" % testbed_name)
        log.info("Tenant List:")
        for project in cl.list_tenants():
            try:
                log.info("Checking Project %s" % project.name)
                log.info("Checking project %s" % project.id)
                images = cl.list_images(project.id)
                paths = '/etc/softfire/images/cirros-0.4.0-x86_64-disk.img'
                for list in image_names:
                    #print(list)
                    for img in images:
                        if (list == img.name):
                            print("Image Matched", list)
                        elif (img.name != list):
                            print('Not matched', img.name)
                            cl.upload_image(list, paths)
                            # log.debug([img.name for img in images])
            except Unauthorized:
                log.warning("Not authorized on project %s" % project.name)


if __name__ == '__main__':
    logging.config.fileConfig("etc/logging.ini", disable_existing_loggers=False)
    parser = argparse.ArgumentParser(description='check Open Stack tenants for softfire')
    parser.add_argument('--os-cred', help='openstack credentials file',
                        default='/etc/softfire/openstack-credentials.json')
    args = parser.parse_args()

    openstack_credentials = args.os_cred  # "/etc/softfire/openstack-credentials.json"
    testbeds = {}
    with open(openstack_credentials, "r") as f:
        testbeds = json.loads(f.read())

    search_images(testbeds)
