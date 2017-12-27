import argparse
import json
import logging.config
import os

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


def search(testbeds, config):
    log.info("Starting the Check Os tool...")
    for testbed_name, testbed in testbeds.items():
        cl = OSClient(testbed_name=testbed_name, testbed=testbed)
        log.info("Checking Testbed %s" % testbed_name)
        if (config.get("images")).get(testbed_name):
            log.info("Tenant List:")
            for project in cl.list_tenants():
                log.info("Check & Update Images")
                check_and_upload_images(cl, config.get("images").get(testbed_name), config.get("images").get("any"), project.id, project.name)


        if (config.get("security_group")).get(testbed_name):
            ignored_tenants = []
            ignored_tenants.extend(config.get('ignore_tenants').get(testbed_name))
            ignored_tenants.extend(config.get('ignore_tenants').get('any'))
            ignored_tenants = set(ignored_tenants)
            ignored_tenants = list(ignored_tenants)
            for project in cl.list_tenants():
                if project.name not in ignored_tenants:
                    log.info("Check & Update Security Group")
                    check_and_add_sec_grp(cl, config.get("security_group").get(testbed_name), config.get("security_group").get("any"), project.id, project.name)
                else:
                    log.info("Ignoring Project: %s" % project.name)

        if (config.get("networks")).get(testbed_name):
            for project in cl.list_tenants():
                log.info("Check Networks")
                check_networks(cl, config.get("networks").get(testbed_name), project.id, project.name)

        if (config.get("ignore_floating_ips")).get(testbed_name):
            for project in cl.list_tenants():
                log.info("Check Floating IPs")
                check_floating_ips(cl, config.get("ignore_floating_ips").get(testbed_name), config.get("ignore_floating_ips").get("any"), project.id, project.name)

def check_networks(cl, networks, project_id, project_name=""):
        try:
            log.info("Checking project %s (%s)" % (project_name, project_id))
            os_networks = cl.list_networks(project_id)
            #os_networks = cl.list_networks("8abb2544e73349d49a1f182254b890c2")
            network = os_networks.get("networks")
            for net in network:
                for n in networks:
                    shared = str(net.get("shared"))
                    router = str(net.get("router:external"))
                    if ((net.get("name") == n.get("name")) and (shared == n.get("shared")) and (router == n.get("router:external"))):
                        log.debug("Matching Network Found", n)
                    else:
                        log.debug("Network not Matched", n)
        except Unauthorized:
            log.warning("Not authorized on project %s" % project_id)

def check_floating_ips(cl, ignore_floatingip, ignore_floatingip_any, project_id, project_name=""):
    try:
        log.info("Checking project %s (%s)" % (project_name, project_id))
        ignore_floatingip_any.extend(ignore_floatingip)
        ignore_floatingip_any = set(ignore_floatingip_any)
        ignore_floatingip_any = list(ignore_floatingip_any)
        flt_ip = cl.list_floatingips(project_id)
        #flt_ip= (cl.list_floatingips("399adcf362f246ae9b8b57a49943baf3"))
        #flt_ip = cl.list_floatingips("8abb2544e73349d49a1f182254b890c2")
        #print("Hello", cl.list_floatingips("8abb2544e73349d49a1f182254b890c2"))
        float_ip = flt_ip.get("floatingips")
        for fip in float_ip:
            if fip.get("floating_ip_address") in ignore_floatingip_any:
                log.debug("Ignore Floating IP", fip.get("floating_ip_address"))
            else:
                log.debug("Floating IP not ignored list")
                if (str(fip.get("fixed_ip_address")) == "None"):
                    cl.release_floating_ips(project_id)
                    log.debug("Floating IP released")
                else:
                    log.debug("Floating ID Allocated")
    except Unauthorized:
        log.warning("Not authorized on project %s" % project_id)



def check_and_upload_images(cl, images, img_any, project_id, project_name=""):
    try:
        log.info("Checking project %s (%s)" % (project_name, project_id))
        openstack_image_names = []
        images_to_upload = []
        img_any.update(images)
        os_images = cl.list_images(project_id)
        for img in os_images:
            openstack_image_names.append(img.name)
        for image in img_any:
            if image in openstack_image_names:
                log.debug("Image Matched")
                #print("matched", image)
            else:
                log.debug('Not matched: %(name)s' % image)
                #print("upload", image)
                images_to_upload.append(image)
                log.debug([img.name for img in images])
        if images_to_upload:
            log.info("Uploading images...")
            for image_to_upload in images_to_upload:
                location = img_any.get(image_to_upload).get('path')
                cl.upload_image(image_to_upload, location)
                #log.info("Successfully Uploaded: %s file: %s" % (image_to_upload.get("name"), location))
    except Unauthorized:
        log.warning("Not authorized on project %s" % project_id)


def check_and_add_sec_grp(cl, sec_grp, sec_grp_any, project_id, project_name=""):
    try:
        log.info("Checking project %s (%s)" % (project_name, project_id))
        openstack_security_groups = []
        sec_grp_any.extend(sec_grp)
        sec_grp_any = set(sec_grp_any)
        sec_grp_any = list(sec_grp_any)
        os_secgrp = cl.list_sec_group(project_id)
        #os_secgrp = (cl.list_sec_group("399adcf362f246ae9b8b57a49943baf3"))
        #os_secgrp = (cl.list_sec_group("8abb2544e73349d49a1f182254b890c2"))
        #log.debug("List Security Groups", os_secgrp)
        for sec in os_secgrp:
            openstack_security_groups.append(sec.get('name'))
            for secg in sec_grp_any:
                if secg in openstack_security_groups:
                    log.debug('Security Group Matched', sec)
                    #print("matched SG", secg)
                else:
                    log.debug('Security Group Not Matched %s' % sec)
                    #print("Not Matched", secg)
                    cl.create_security_group(sec.get("tenant_id"), secg)

    except Unauthorized:
        log.warning("Not authorized on project %s" % project_id)


def main():
    logging.basicConfig(level=logging.DEBUG)
    #logging.config.fileConfig("etc/logging.ini", disable_existing_loggers=False)
    parser = argparse.ArgumentParser(description='check Open Stack tenants for softfire')
    parser.add_argument('--os-cred',
                        help='openstack credentials file',
                        default='/etc/softfire/openstack-credentials.json')
    parser.add_argument("-d", "--debug", help="show debug prints", action="store_true")
    parser.add_argument('--config', help='config json file',
                        default='/etc/softfire/config_list.json')

    args = parser.parse_args()

    openstack_credentials = args.os_cred  # '/etc/softfire/openstack-credentials.json'
    config = args.config

    print()
    if args.debug:
        logging_file = "etc/logging.ini"
        if os.path.isfile(logging_file):
            logging.config.fileConfig(logging_file)
        else:
            logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    with open(openstack_credentials, "r") as f:
        testbeds = json.loads(f.read())
    with open(config, "r") as f:
        config = json.loads(f.read())
        search(testbeds, config)

#/net/u/dsa/Projects/Softfire/check-os/etc/config_list.json
#'/etc/softfire/config_list.json'
#"/net/u/dsa/Projects/Softfire/check-os/etc/logging.ini"   #"etc/logging.ini"

