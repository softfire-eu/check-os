import argparse
import json
import logging.config

from keystoneauth1.exceptions import Unauthorized

from sdk.softfire.os_utils import OSClient

log = logging.getLogger(__name__)


# def image_list():
#     file_path = '/net/u/dsa/Projects/Softfire/check-os/etc/images_list.json'
#     image_names = []
#     with open(file_path, "r") as f:
#         images = json.loads(f.read())
#     for key, val in images.items():
#         # print(val)
#         for i in val:
#             image_names.append(i.get('name'))
#     return image_names


# def path(name, path):
#     file_path = path
#     with open(file_path, "r") as f:
#         images = json.loads(f.read())
#     for key, val in images.items():
#         # print(val)
#         for i in val:
#             if i.get('name') == name:
#                 paths = i.get('path')
#     return paths


def search_images(testbeds, images):
    for testbed_name, testbed in testbeds.items():
        cl = OSClient(testbed_name=testbed_name, testbed=testbed)
        log.info("Checking Testbed %s" % testbed_name)
        if images.get(testbed_name):
            log.info("Tenant List:")
            for project in cl.list_tenants():
                check_and_upload_images(cl, images.get(testbed_name), project.id, project.name)


def check_and_upload_images(cl, images, project_id, project_name=""):
    try:
        log.info("Checking project %s (%s)" % (project_name, project_id))
        openstack_image_names = []
        images_to_upload = []
        os_images = cl.list_images(project_id)
        for img in os_images:
            openstack_image_names.append(img.name)
        for image in images:
            if image.get("name") in openstack_image_names:
                log.debug('Image Matched %(name)s'% image)
            else:
                log.debug('Not matched: %(name)s'% image)
                images_to_upload.append(image)
                # log.debug([img.name for img in images])
        if images_to_upload:
            log.info("Uploading images...")
            for image_to_upload in images_to_upload:
                location = image_to_upload.get("path")
                cl.upload_image(image_to_upload.get("name"), location)
                log.info("Succesfully Uploaded: %s file: %s"% ( image_to_upload.get("name"), location))
    except Unauthorized:
        log.warning("Not authorized on project %s" % project_id)


def main():
    logging.config.fileConfig("etc/logging.ini", disable_existing_loggers=False)
    parser = argparse.ArgumentParser(description='check Open Stack tenants for softfire')
    parser.add_argument('--os-cred', help='openstack credentials file',
                        default='/etc/softfire/openstack-credentials.json')
    parser.add_argument('--images', help='image config json file',
                        default='/etc/softfire/images.json')
    args = parser.parse_args()

    openstack_credentials = args.os_cred  # "/etc/softfire/openstack-credentials.json"
    image_config = args.images
    testbeds = {}
    with open(openstack_credentials, "r") as f:
        testbeds = json.loads(f.read())
    with open(image_config, "r") as f:
        images = json.loads(f.read())
    search_images(testbeds, images)
