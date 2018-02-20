import argparse
import json
import logging.config
import os
import sys
import time
import yaml

from keystoneauth1.exceptions import Unauthorized
from org.openbaton.sdk.client import OBClient

from sdk.softfire.exp_man_client import ExpManClient
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


def check_testbeds(testbeds, config, check_images, check_security_group, check_networks, check_floating_ip,
                   check_vm_zombie, dry_run, experimenter=None):
    """
    :param testbeds:
    :param config:
    :param check_images:
    :param check_security_group:
    :param check_networks:
    :param check_floating_ip:
    :param check_vm_zombie:
    :param dry_run:
    :param experimenter: if not None, then checks are only executed for this experimenter name
    :return:
    """
    log.info("Starting the Check OS tool...")
    nsd_results = {}
    nsr_results = {}
    vm_results = {}
    check_vm_zombie_exceptions = {}
    ignored_projects_in_any_tb = config.get('ignore_projects').get('any') if config.get(
        'ignore_projects') is not None and config.get('ignore_projects').get('any') is not None else []
    fip_results = {}
    for testbed_name, testbed in testbeds.items():
        try:
            cl = OSClient(testbed_name, testbed, None, testbed.get("admin_project_id"))
        except Exception as e:
            log.error('Exception while creating the OpenStack client for testbed {}: {}'.format(testbed_name, e))
            log.warning('Skipping testbed {}.'.format(testbed_name))
            continue
        log.info("Checking Testbed %s" % testbed_name)
        ignored_projects = config.get('ignore_projects').get(testbed_name) if config.get(
            'ignore_projects') is not None and config.get('ignore_projects').get(
            testbed_name) is not None else []
        ignored_projects.extend(ignored_projects_in_any_tb)

        if check_images:
            log.info("~~~~~~~~~~~~~~~~~~~~Check & Update Images~~~~~~~~~~~~~~~~~~~~~~")
            for project in cl.list_tenants():
                if experimenter is not None and project.name != experimenter:
                    continue
                if project.name in ignored_projects:
                    log.info('Ignoring project {}'.format(project.name))
                    continue
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
            for project in cl.list_tenants():
                if experimenter is not None and project.name != experimenter:
                    continue
                if project.name not in ignored_projects:
                    sg = check_and_add_sec_grp(cl, config.get("security_group").get(testbed_name),
                                               config.get("security_group").get("any"), project.id, project.name)
                    sec_grp_list.append(sg)
                else:
                    log.info("Ignoring project %s" % project.name)
            log.info("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")

        if check_networks:
            log.info("~~~~~~~~~~~~~~~~~~~~Check Networks~~~~~~~~~~~~~~~~~~~~~~")
            for project in cl.list_tenants():
                if experimenter is not None and project.name != experimenter:
                    continue
                if project.name in ignored_projects:
                    log.info('Ignoring project {}'.format(project.name))
                    continue
                net = check_os_networks(cl, config.get("networks").get(testbed_name), project.id, project.name)

                network_list.append(net)
            log.info("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")

        if check_floating_ip:
            log.info("~~~~~~~~~~~~~~~~~~~~Check Floating Ips~~~~~~~~~~~~~~~~~~~~~~")
            log.debug('Testbed: {}'.format(testbed_name))
            try:
                for project in cl.list_tenants():
                    if experimenter is not None and project.name != experimenter:
                        continue
                    if project.name in ignored_projects:
                        log.info('Ignoring project {}'.format(project.name))
                        continue
                    released_fips, exception = check_floating_ips(cl, project.id, project.name, config.get("ignore_floating_ips").get(testbed_name),
                                             config.get("ignore_floating_ips").get("any"),
                                             dry_run)
                    if fip_results.get(testbed_name) is None:
                        fip_results[testbed_name] = {}
                    if fip_results.get(testbed_name).get(project.name) is None:
                        fip_results.get(testbed_name)[project.name] = {'released': [], 'exceptions':[]}
                    if released_fips is not None:
                        fip_results.get(testbed_name).get(project.name).get('released').extend(released_fips)
                    else:
                        fip_results.get(testbed_name).get(project.name).get('exceptions').append(exception)
            except Exception as e:
                log.error('Exception while checking floating IPs on testbed {}: {}'.format(testbed_name, e))
            log.info("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")

        if check_vm_zombie and config.get("check-vm") and config.get("check-vm").get(
                "experiment-manager") and config.get("check-vm").get("nfvo"):
            log.info("~~~~~~~~~~~~~~~~~~~~~~~~Check VMs~~~~~~~~~~~~~~~~~~~~~~~~~~~")
            try:
                nsds, nsrs, vms = check_vm_os(cl,
                                              config.get("check-vm").get("experiment-manager"),
                                              config.get("check-vm").get("nfvo"),
                                              testbed_name,
                                              config.get("check-vm").get("ignore-vm-ids"),
                                              config.get("check-vm").get("ignore-nsr-ids"),
                                              ignored_projects=ignored_projects,
                                              dry=dry_run,
                                              experimenter=experimenter)
                nsd_results = {**nsd_results, **nsds}
                nsr_results = {**nsr_results, **nsrs}
                vm_results = {**vm_results, **vms}
            except Exception as e:
                log.error('Exception while checking VMs on testbed {}: {}'.format(testbed_name, e))
                check_vm_zombie_exceptions[testbed_name] = e
                master.append(False)

            log.info("~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
    master.extend(sec_grp_list)
    master.extend(network_list)
    master.extend(float_list)
    master.extend(image_list)
    if check_vm_zombie:
        print_check_vm_os_results(nsd_results, nsr_results, vm_results, check_vm_zombie_exceptions)
    if check_floating_ip:
        print_fip_results(fip_results)
    if check_networks:
        print("Networks Not Found", network_not_matched_list)
    if check_security_group:
        print("Security Groups Not Found", sec_grp_not_matched_list)
    if check_images:
        print("Images Uploaded", images_uploaded)
    if False in master:
        sys.exit(1)


def print_check_vm_os_results(nsd_results, nsr_results, vm_results, exceptions):
    print('~~~~~~~~~~~~~~~~~~~~~ Check for Zombie VMs ~~~~~~~~~~~~~~~~~~~~~~~~')
    projects = list(set([nsd_results.get(x).get('project') for x in nsd_results]
                        + [nsr_results.get(x).get('project') for x in nsr_results]
                        + [vm_results.get(x).get('project') for x in vm_results]))
    testbeds = list(set([vm_results.get(x).get('testbed') for x in vm_results]))

    if len(nsd_results) + len(nsr_results) > 0:
        print('======== NSDs and NSRs ========\n')
        for project in projects:
            deleted_nsrs_in_project = [nsr for nsr in nsr_results if
                                       nsr_results.get(nsr).get('project') == project and nsr_results.get(nsr).get(
                                           'successful')]
            failed_nsrs_in_project = [nsr for nsr in nsr_results if
                                      nsr_results.get(nsr).get('project') == project and nsr_results.get(nsr).get(
                                          'successful') is False]
            deleted_nsds_in_project = [nsd for nsd in nsd_results if
                                       nsd_results.get(nsd).get('project') == project and nsd_results.get(nsd).get(
                                           'successful')]
            failed_nsds_in_project = [nsd for nsd in nsd_results if
                                      nsd_results.get(nsd).get('project') == project and nsd_results.get(nsd).get(
                                          'successful') is False]

            if len(deleted_nsrs_in_project + failed_nsrs_in_project +
                           deleted_nsds_in_project + failed_nsds_in_project) == 0:
                continue
            print('Project {}'.format(project))

            if len(deleted_nsrs_in_project + failed_nsrs_in_project) > 0:
                print('  NSRs')
            if len(deleted_nsrs_in_project) > 0:
                print('    Removed {}: {}'.format(len(deleted_nsrs_in_project), ', '.join(deleted_nsrs_in_project)))
            if len(failed_nsrs_in_project) > 0:
                print('    Failed to remove {}: {}'.format(len(failed_nsrs_in_project),
                                                           ', '.join(failed_nsrs_in_project)))

            if len(deleted_nsds_in_project + failed_nsds_in_project) > 0:
                print('  NSDs')
            if len(deleted_nsds_in_project) > 0:
                print('    Removed {}: {}'.format(len(deleted_nsds_in_project), ', '.join(deleted_nsds_in_project)))
            if len(failed_nsds_in_project) > 0:
                print('    Failed to remove {}: {}'.format(len(failed_nsds_in_project),
                                                           ', '.join(failed_nsds_in_project)))
            print('')
        print('')

    if len(vm_results) > 0:
        print('============= VMs =============\n')
        for testbed in testbeds:
            vm_projects = list(set(
                [vm.get('project') for vm in [vm_results.get(vm) for vm in vm_results] if
                 vm.get('testbed') == testbed]))
            if len(vm_projects) == 0:
                continue
            print('Testbed {}'.format(testbed))
            for project in vm_projects:
                deleted_vms_in_project = [vm for vm in vm_results if
                                          vm_results.get(vm).get('testbed') == testbed and vm_results.get(vm).get(
                                              'project') == project and vm_results.get(vm).get('successful')]
                failed_vms_in_project = [vm for vm in vm_results if
                                         vm_results.get(vm).get('testbed') == testbed and vm_results.get(vm).get(
                                             'project') == project and vm_results.get(vm).get('successful') is False]
                if len(deleted_vms_in_project) + len(failed_vms_in_project) == 0:
                    continue
                print('  Project {}'.format(project))
                if len(deleted_vms_in_project) > 0:
                    print('    Removed {}: {}'.format(len(deleted_vms_in_project), ', '.join(deleted_vms_in_project)))
                if len(failed_vms_in_project) > 0:
                    print(
                        '    Failed to remove {}: {}'.format(len(failed_vms_in_project),
                                                             ', '.join(failed_vms_in_project)))
            print('')
        print('')

    if len(exceptions) > 0:
        print('========= Exceptions ==========\n')
        for testbed in exceptions:
            print('Testbed {}'.format(testbed))
            print('  {}\n'.format(exceptions.get(testbed)))

def print_fip_results(fip_results):
    print('~~~~~~~~~~~~~~~~~~~~ Check floating IPs ~~~~~~~~~~~~~~~~~~~~~~~')
    for tb in fip_results:
        print('Testbed {}'.format(tb))
        for project in fip_results.get(tb):
            if len(fip_results.get(tb).get(project).get('released')) + len(fip_results.get(tb).get(project).get('exceptions')) > 0:
                print('  Project {}'.format(project))
                if len(fip_results.get(tb).get(project).get('released')) > 0:
                    print('    Released floating IPs: {}'.format(', '.join(fip_results.get(tb).get(project).get('released'))))
                if len(fip_results.get(tb).get(project).get('exceptions')) > 0:
                    print('    Exceptions: {}'.format(', '.join(fip_results.get(tb).get(project).get('exceptions'))))
        print()


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
        os_net_names = [net.get("name") for net in os_networks]
        log.debug("Found networks: %s" % os_net_names)
        for n in networks:
            found = False
            for os_net in os_networks:
                shared = os_net.get("shared")
                router = os_net.get("router:external")
                if ((os_net.get("name") == n.get("name"))
                    and (shared == n.get("shared"))
                    and (router == n.get("router:external"))):
                    found = True
                    break
            if not found:
                network_not_matched_list.append(os_networks)
        if network_not_matched_list:
            log.error("Missing networks: %s" % network_not_matched_list)
            return False
        return True
    except Unauthorized:
        log.warning("Not authorized on project %s" % project_id)


def check_floating_ips(cl, project_id, project_name="", ignore_floatingip=[], ignore_floatingip_any=[], dry_run=False):
    """
    :param cl:
    :param project_id:
    :param project_name:
    :param ignore_floatingip:
    :param ignore_floatingip_any:
    :param dry_run:
    :return: ([removed_fip_addresses], exception) exception is None if no exception occured, otherwise [removed_fip_addresses] is None
    """
    try:
        log.info("Checking project %s (%s)" % (project_name, project_id))
        ignore_floatingip = ignore_floatingip or []
        ignore_floatingip_any = ignore_floatingip_any or []
        ignore_floatingip_any.extend(ignore_floatingip)
        ignore_floatingip_any = set(ignore_floatingip_any)
        log.debug("Ignoring floating ips: %s" % ignore_floatingip_any)
        floating_ips = cl.list_floatingips(project_id)
        log.debug("List of all floating IPs allocated to project %s: %s" % (
            project_name, ', '.join([f.get("floating_ip_address") for f in floating_ips])))
        ignored_fips_ids = list()
        for fip in floating_ips:
            if fip.get("floating_ip_address") in ignore_floatingip_any:
                log.debug("Ignore Floating IP %s because it is in ignore list" % fip.get("floating_ip_address"))
                ignored_fips_ids.append(fip.get("id"))
            elif fip.get("fixed_ip_address") is None:
                log.debug("Floating IP to be released: %s" % fip.get("floating_ip_address"))
            else:
                log.debug("Ignoring Floating IP %s because it is allocated" % fip.get("floating_ip_address"))
                ignored_fips_ids.append(fip.get("id"))
        all_fips = cl.list_floatingips(project_id)
        remove_fips = [fip for fip in all_fips if fip.get('id') not in ignored_fips_ids]
        remove_fip_addresses = [fip.get('floating_ip_address') for fip in remove_fips]
        if not dry_run:
            cl.release_floating_ips(project_id, keep_fip_id_list=ignored_fips_ids)
        else:
            if len(remove_fip_addresses) > 0:
                log.info('Releasing the following floating IPs in project {}: {}'.format(project_name, ', '.join(
                    remove_fip_addresses)))
        return remove_fip_addresses, None
    except Unauthorized as ex:
        log.warning("Not authorized on project %s" % project_id)
        log.error("Exception: ", ex)
        return None, ex
    except Exception as e:
        log.error('Exception while checking floating IPs on project {}: {}'.format(project_name, e))
        return None, e


def _check_resource(resource, nsr_to_keep, vms_to_keep,  project_name, testbed):
    if resource.get('username') != project_name or resource.get('node_type') not in ['NfvResource', 'SecurityResource', 'MonitoringResource']:
        return

    res_str = resource.get("value")
    try:
        value = json.loads(res_str)
    except Exception as e:
        log.debug('Resource value: {}'.format(res_str))
        log.error(
            'Exception while parsing value of resource {} of experiment {}: {}'.format(resource.get('resource_id'),
                                                                                       resource.get(
                                                                                           'experiment_id'),
                                                                                       e))
        return

    if resource.get('node_type') == 'NfvResource':
        nsr_id = value.get('id')
        if nsr_id is not None and nsr_id != '':
            log.debug('Softfire knows of NSR with ID {}'.format(nsr_id))
            nsr_to_keep.append(nsr_id)
        else:
            if resource.get('status') != 'RESERVED':
                log.warning('Expected an NSR ID for NFV resource {} in experiment {}, but it was None or empty string.'.format(
                    resource.get('resource_id'), resource.get('experiment_id')))
    elif resource.get('node_type') == 'SecurityResource':
        nsr_id = value.get('nsr_id')
        if nsr_id is None or nsr_id == '':
            if resource.get('status') != 'RESERVED':
                log.warning('Expected an NSR ID for security resource {} in experiment {}, but it was None or empty string.'.format(
                    resource.get('resource_id'), resource.get('experiment_id')))
        else:
            nsr_to_keep.append(nsr_id)
    elif resource.get('node_type') == 'MonitoringResource':
        testbed_name = value.get('testbed')
        if testbed_name is None or testbed_name == testbed:
            vm_id = value.get('vm_id')
            if vm_id is not None and vm_id != '':
                vms_to_keep.append(vm_id)
            else:
                if resource.get('status') != 'RESERVED':
                    log.warning('Expected a VM ID for monitoring resource {} in experiment {}, but it was None or empty string.'.format(
                        resource.get('resource_id'), resource.get('experiment_id')))


def check_vm_os(cl, exp_man_dict, nfvo_dict, testbed_name, vms_to_keep_arg=[], nsrs_to_keep_arg=[],
                ignored_projects=[],
                dry=False, experimenter=None):
    """
    :param cl:
    :param exp_man_dict:
    :param nfvo_dict:
    :param testbed_name: only used for documenting the results of the VM removal correctly
    :param vms_to_keep_arg:
    :param nsrs_to_keep_arg:
    :param ignored_projects:
    :param dry:
    :param experimenter: if not None, then the check is only performed for this experimenter name
    :return: (nsds, nsrs, vms) a tuple containing the results of the removals of the nsds, nsrs and vms
    """

    exp_man_cl = ExpManClient(username=exp_man_dict.get("username"),
                              password=exp_man_dict.get("password"),
                              experiment_manager_ip=exp_man_dict.get("ip"),
                              experiment_manager_port=exp_man_dict.get("port"),
                              debug=exp_man_dict.get("debug", "true").lower() == "true")

    experimenters = exp_man_cl.get_all_experimenters()

    nsds = {}
    nsrs = {}
    vms = {}
    for project in cl.list_tenants():
        if experimenter is not None and project.name != experimenter:
            continue
        vms_to_keep = vms_to_keep_arg
        nsrs_to_keep = nsrs_to_keep_arg
        if project.name not in experimenters:
            log.debug("Skipping project %s not belonging to softfire" % project.name)
            continue
        elif project.name in ignored_projects:
            log.info('Ignoring project {}'.format(project.name))
            continue
        else:
            log.info("Executing check VM on project %s" % project.name)
        project_name = project.name
        resources = exp_man_cl.get_all_resources()
        ob_client = OBClient(nfvo_ip=nfvo_dict.get("ip"),
                             nfvo_port=nfvo_dict.get("port"),
                             username=nfvo_dict.get("username"),
                             password=nfvo_dict.get("password"),
                             https=nfvo_dict.get("https", "false").lower() == "true",
                             project_name=project_name)
        if not ob_client.project_id:
            log.warning("Openstack project %s was not found on OB so it will be skipped." % project_name)
            continue
        for res in [res for res in resources if res.get('username') == project_name]:
            if type(res) is list:
                for r in res:
                    _check_resource(r, nsrs_to_keep, vms_to_keep, project_name, testbed_name)
            else:
                _check_resource(res, nsrs_to_keep, vms_to_keep, project_name, testbed_name)

        ob_nsrs = ob_client.list_nsrs()
        nsrs_to_remove = [nsr for nsr in ob_nsrs if nsr.get("id") not in nsrs_to_keep]
        nsrs_to_keep = [nsr for nsr in ob_nsrs if nsr.get("id") in nsrs_to_keep]
        nsd_ids_to_keep = [nsr.get('descriptor_reference') for nsr in nsrs_to_keep]
        for nsr in nsrs_to_remove:
            if dry:
                nsrs[nsr.get('id')] = {'project': project_name, 'successful': True}
            else:
                try:
                    ob_client.delete_nsr(nsr.get("id"))
                    nsrs[nsr.get('id')] = {'project': project_name, 'successful': True}
                except Exception as e:
                    log.error('Exception while deleting the NSR {}: {}'.format(nsr.get('id'), e))
                    nsrs[nsr.get('id')] = {'project': project_name, 'successful': False}
                time.sleep(2)
            nsd_id = nsr.get('descriptor_reference')
            if nsd_id not in nsd_ids_to_keep:
                if dry:
                    nsds[nsd_id] = {'project': project_name, 'successful': True}
                else:
                    try:
                        ob_client.delete_nsd(nsd_id)
                        nsds[nsd_id] = {'project': project_name, 'successful': True}
                    except Exception as e:
                        log.error('Exception while deleting the NSD {}: {}'.format(nsr.get('descriptor_reference'), e))
                        nsds[nsd_id] = {'project': project_name, 'successful': False}

        for nsr in nsrs_to_keep:
            for vnfr in nsr.get("vnfr"):
                for vdu in vnfr.get("vdu"):
                    for vnfci in vdu.get("vnfc_instance"):
                        if vnfci.get("vc_id"):
                            vms_to_keep.append(vnfci.get("vc_id"))

        for vm in cl.list_server(cl.get_project_from_name(project_name).id):
            if vm.id not in vms_to_keep:
                if dry:
                    vms[vm.id] = {'testbed': testbed_name, 'project': project_name, 'successful': True}
                else:
                    try:
                        log.debug('Removing VM {}'.format(vm.id))
                        # TODO passing the project ID does not make sense; consider changing the SDK
                        cl.delete_server(vm.id, ob_client.project_id)
                        vms[vm.id] = {'testbed': testbed_name, 'project': project_name, 'successful': True}
                    except Exception as e:
                        log.error('Exception while deleting VM {}: {}'.format(vm.id, e))
                        vms[vm.id] = {'testbed': testbed_name, 'project': project_name, 'successful': False}
    return nsds, nsrs, vms


def main():
    logging_file = "etc/logging.ini"
    parser = argparse.ArgumentParser(description='check Open Stack tenants for softfire')
    parser.add_argument('--os-cred',
                        help='openstack credentials file',
                        default='/etc/softfire/openstack-credentials.json')

    parser.add_argument("-d", "--debug", help="show debug prints", action="store_true")
    parser.add_argument('--config', help='config yaml file', default='/etc/softfire/checkos_config.yml')

    parser.add_argument("-F", "--check-floating-ip", help="release unused floating ips", action="store_true")
    parser.add_argument("-N", "--check-networks", help="check and create networks", action="store_true")
    parser.add_argument("-I", "--check-images", help="check and upload images", action="store_true")
    parser.add_argument("-Z", "--check-vm-zombie", help="check and delete zombie vms", action="store_true")
    parser.add_argument("-S", "--check-security-group", help="check and create for a specific security group",
                        action="store_true")
    parser.add_argument("-e", "--experimenter", help="perform checks only for the given experimenter name")
    parser.add_argument("-t", "--testbed", help="perform checks only on the given testbed")

    parser.add_argument("-dry", "--dry-run", help="Execute dry run", action="store_true", default=False)

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
    if args.testbed is not None:
        testbed_names = list(testbeds.keys())
        for testbed in testbed_names:
            if testbed != args.testbed:
                testbeds.pop(testbed)
        if len(testbeds) == 0:
            log.warning('No testbed with name {} found in file {}'.format(args.testbed, openstack_credentials))
    with open(config, "r") as f:
        config_dict = yaml.load(f)
        check_testbeds(testbeds, config_dict, args.check_images, args.check_security_group, args.check_networks,
                       args.check_floating_ip, args.check_vm_zombie, dry_run=args.dry_run,
                       experimenter=args.experimenter)
