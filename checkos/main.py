import argparse
import json
import logging.config
import os
import sys
import time

from keystoneauth1.exceptions import Unauthorized
from sdk.softfire.os_utils import OSClient

log = logging.getLogger(__name__)

image_list = list()
sec_grp_list = list()
network_list = list()
float_list = list()
master = list()

network_not_matched_list = list()
sec_grp_not_matched_list = list()
images_uploaded = list()


def check_testbeds(testbeds, config, check_images, check_security_group, check_networks, check_floating_ip, dry_run):
    log.info("Starting the Check Os tool...")
    for testbed_name, testbed in testbeds.items():
        cl = OSClient(testbed_name, testbed, None, testbed.get("admin_project_id"))
        log.info("Checking Testbed %s" % testbed_name)

        if check_images:
            log.info("~~~~~~~~~~~~~~~~~~~~Check & Update Images~~~~~~~~~~~~~~~~~~~~~~")
            for project in cl.list_tenants():
                im = check_and_upload_images(cl,
                                             config.get("images").get(testbed_name),
                                             config.get("images").get("any"),
                                             project.id,
                                             project.name,
                                             dry_run)

                image_list.append(im)
            log.info("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")

        if check_security_group:
            log.info("~~~~~~~~~~~~~~~~~~~~Check & Update Security Group~~~~~~~~~~~~~~~~~~~~~~")
            ignored_tenants = []
            ignored_tenants.extend(config.get('ignore_tenants').get(testbed_name))
            ignored_tenants.extend(config.get('ignore_tenants').get('any'))
            ignored_tenants = set(ignored_tenants)
            for project in cl.list_tenants():
                if project.name not in ignored_tenants:
                    sg = check_and_add_sec_grp(cl, config.get("security_group").get(testbed_name),
                                               config.get("security_group").get("any"), project.id, project.name)
                    sec_grp_list.append(sg)
                else:
                    log.info("Ignoring Project: %s" % project.name)
            log.info("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")

        if check_networks:
            log.info("~~~~~~~~~~~~~~~~~~~~Check Networks~~~~~~~~~~~~~~~~~~~~~~")
            for project in cl.list_tenants():
                net = check_os_networks(cl, config.get("networks").get(testbed_name), project.id, project.name)

                network_list.append(net)
            log.info("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")

        if check_floating_ip:
            log.info("~~~~~~~~~~~~~~~~~~~~Check Floating Ips~~~~~~~~~~~~~~~~~~~~~~")
            for project in cl.list_tenants():
                fip = check_floating_ips(cl, config.get("ignore_floating_ips").get(testbed_name),
                                         config.get("ignore_floating_ips").get("any"),
                                         project.id,
                                         project.name,
                                         dry_run)

                float_list.append(fip)
            log.info("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")

    master.extend(sec_grp_list)
    master.extend(network_list)
    master.extend(float_list)
    master.extend(image_list)
    print("Networks Not Found", network_not_matched_list)
    print("Security Group Not Found", sec_grp_not_matched_list)
    print("Images Uploaded", images_uploaded)
    # print("Fip Uploaded", fip_released)
    if False in master:
        sys.exit(1)


def check_and_upload_images(cl, images, img_any, project_id, project_name="", dry_run=False):
    try:
        log.info("Checking project %s (%s)" % (project_name, project_id))
        images_to_upload = []
        img_any.update(images)
        os_images = cl.list_images(project_id)
        openstack_image_names = [img.name for img in os_images]
        for image in img_any:
            if image in openstack_image_names:
                log.debug("Image %s is available" % image)
            else:
                log.debug('Image %s is not available' % image)
                images_to_upload.append(image)

        log.debug("Images to upload are: %s" % images_to_upload)
        if images_to_upload:
            for image_to_upload in images_to_upload:
                location = img_any.get(image_to_upload).get('path')
                if not dry_run:
                    cl.upload_image(image_to_upload, location)
                else:
                    log.info("Executing cl.upload_image(image_to_upload, location)...")
                    time.sleep(2)
                log.info("Successfully Uploaded: %s file: %s" % (image_to_upload, location))
        return True
    except Unauthorized:
        log.warning("Not authorized on project %s" % project_id)
        return False


def check_and_add_sec_grp(cl, sec_grp, sec_grp_any, project_id, project_name=""):
    try:
        log.info("Checking project %s (%s)" % (project_name, project_id))
        sec_grp_any.extend(sec_grp)
        sec_grp_any = set(sec_grp_any)
        os_secgrp = cl.list_sec_group(project_id)

        openstack_security_groups = [sec.get('name') for sec in os_secgrp]
        for secg in sec_grp_any:
            if secg in openstack_security_groups:
                log.debug('Security Group already present %s' % secg)
            else:
                log.debug('Security Group missing %s' % secg)
                sec_grp_not_matched_list.append(secg)
                # cl.create_security_group(sec.get("tenant_id"), secg)
        if sec_grp_not_matched_list:
            return False
        return True

    except Unauthorized:
        log.warning("Not authorized on project %s" % project_id)
        return False


def check_os_networks(cl, networks, project_id, project_name=""):
    try:
        log.info("Checking project %s (%s)" % (project_name, project_id))
        os_networks = cl.list_networks(project_id)
        log.debug("Found networks: %s" % [net.get("name") for net in os_networks])
        for net in os_networks:
            for n in networks:
                shared = str(net.get("shared"))
                router = str(net.get("router:external"))
                if ((net.get("name") == n.get("name")) and (shared == n.get("shared")) and (
                            router == n.get("router:external"))):
                    log.debug("Found Network: %s" % n)
                else:
                    log.debug("Missing Network: %s" % n)
                    network_not_matched_list.append(n)
        if network_not_matched_list:
            return False
        return True
    except Unauthorized:
        log.warning("Not authorized on project %s" % project_id)


def check_floating_ips(cl, ignore_floatingip, ignore_floatingip_any, project_id, project_name="", dry_run=False):
    try:
        log.info("Checking project %s (%s)" % (project_name.upper(), project_id))
        if not ignore_floatingip_any:
            ignore_floatingip_any = []
        ignore_floatingip_any.extend(ignore_floatingip)
        ignore_floatingip_any = set(ignore_floatingip_any)
        log.debug("Ignoring floating ips: %s" % ignore_floatingip_any)
        floating_ips = cl.list_floatingips(project_id)
        log.debug("List of all floating ip allocated to project %s: %s" % (
            project_name, [f.get("floating_ip_address") for f in floating_ips]))
        ignored_fips_ids = list()
        for fip in floating_ips:
            if fip.get("floating_ip_address") in ignore_floatingip_any:
                log.debug("Ignore Floating IP %s because in ignore list" % fip.get("floating_ip_address"))
                ignored_fips_ids.append(fip.get("id"))
            elif fip.get("fixed_ip_address") is None:
                log.debug("Floating IP to be released: %s" % fip.get("floating_ip_address"))
            else:
                log.debug("Ignoring Floating IP %s because is Allocated" % fip.get("floating_ip_address"))
                ignored_fips_ids.append(fip.get("id"))
        if not dry_run:
            cl.release_floating_ips(project_id, ignored_fips_ids)
        else:
            log.info("Executing 'cl.release_floating_ips(project_id, ignored_fips_ids)'")
            time.sleep(1)
        return True
    except Unauthorized as ex:
        log.warning("Not authorized on project %s" % project_id)
        log.error("Exception: ", ex)
        return False


def main():
    logging_file = "etc/logging.ini"
    parser = argparse.ArgumentParser(description='check Open Stack tenants for softfire')
    parser.add_argument('--os-cred',
                        help='openstack credentials file',
                        default='/etc/softfire/openstack-credentials.json')

    parser.add_argument("-d", "--debug", help="show debug prints", action="store_true")
    parser.add_argument('--config', help='config json file', default='/etc/softfire/config_list.json')

    parser.add_argument("-F", "--check-floating-ip", help="release unused floating ips", action="store_true")
    parser.add_argument("-N", "--check-networks", help="check and create networks", action="store_true")
    parser.add_argument("-I", "--check-images", help="check and upload images", action="store_true")
    parser.add_argument("-S", "--check-security-group", help="check and create for a specific security group",
                        action="store_true")

    parser.add_argument("-dry", "--dry-run", help="Execute dru run", action="store_true", default=False)

    args = parser.parse_args()

    openstack_credentials = args.os_cred  # '/etc/softfire/openstack-credentials.json'
    config = args.config

    print()
    if args.debug:
        if os.path.isfile(logging_file):
            logging.config.fileConfig(logging_file)
        else:
            logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    with open(openstack_credentials, "r") as f:
        testbeds = json.loads(f.read())
    with open(config, "r") as f:
        config_json = json.loads(f.read())
        check_testbeds(testbeds, config_json, args.check_images, args.check_security_group, args.check_networks,
                       args.check_floating_ip, args.dry_run)
