#!/usr/bin/env python3
"""
Azure Container Registry Image Cleanup Script
==============================================

This script automates the cleanup of unused container images in Azure Container Registry (ACR).
It identifies images that are not being used by any App Service in the subscription and
suggests them for deletion (with mock deletion in this version).

Features:
- Works at the manifest level (actual images, not just tags)
- Checks all App Services including deployment slots
- Only considers images older than 30 days
- Uses Azure CLI authentication
- Mock deletion mode for safety

Prerequisites:
- Python 3.7+
- Azure CLI installed and configured (run 'az login' before using)
- Required Python packages: azure-identity, azure-mgmt-containerregistry, azure-mgmt-web
"""

import os
import sys
import json
import subprocess
import platform
import getpass
import socket
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Set, Tuple, Optional
from collections import defaultdict
from pathlib import Path

# Azure SDK imports
try:
    from azure.identity import AzureCliCredential
    from azure.mgmt.containerregistry import ContainerRegistryManagementClient
    from azure.mgmt.web import WebSiteManagementClient
    from azure.core.exceptions import AzureError
except ImportError:
    print("ERROR: Required Azure packages not found.")
    print("Please install them using:")
    print("  pip install azure-identity azure-mgmt-containerregistry azure-mgmt-web")
    sys.exit(1)


# ============================================================================
# CONFIGURATION SECTION
# ============================================================================

# Azure Configuration
#
# This script uses Azure CLI authentication. Before running:
# 1. Install Azure CLI: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli
# 2. Login: az login
# 3. Set your subscription (if needed): az account set --subscription <subscription-id>
#
# Required permissions:
# - Contributor role on the subscription (or at minimum, Reader on subscription + Contributor on ACR)
# - This allows reading App Services and managing Container Registry

SUBSCRIPTION_ID = os.getenv('AZURE_SUBSCRIPTION_ID', '')

# ACR Configuration
ACR_NAME = os.getenv('AZURE_ACR_NAME', '')  # Your Azure Container Registry name
ACR_RESOURCE_GROUP = os.getenv('AZURE_ACR_RESOURCE_GROUP', '')  # Resource group containing the ACR

# Age threshold for image deletion (in days)
IMAGE_AGE_THRESHOLD_DAYS = 30

# Script version for audit trail
SCRIPT_VERSION = "1.0.0"

# Audit directory
AUDIT_DIR = Path("audits")

# ============================================================================
# AUTHENTICATION
# ============================================================================

def validate_configuration():
    """
    Validates that all required configuration values are provided.
    Prompts user for missing values at runtime.

    Returns:
        Tuple of (subscription_id, acr_name, acr_resource_group)
    """
    print("=" * 80)
    print("VALIDATING CONFIGURATION")
    print("=" * 80)
    print()

    # Use global variables but allow runtime override
    subscription_id = SUBSCRIPTION_ID
    acr_name = ACR_NAME
    acr_resource_group = ACR_RESOURCE_GROUP

    # Prompt for missing values
    if not subscription_id:
        print("AZURE_SUBSCRIPTION_ID not found in environment or configuration.")
        subscription_id = input("Please enter your Azure Subscription ID: ").strip()
        if not subscription_id:
            print("\nERROR: Subscription ID is required.")
            sys.exit(1)
        print()

    if not acr_name:
        print("AZURE_ACR_NAME not found in environment or configuration.")
        acr_name = input("Please enter your Azure Container Registry name: ").strip()
        if not acr_name:
            print("\nERROR: ACR Name is required.")
            sys.exit(1)
        print()

    if not acr_resource_group:
        print("AZURE_ACR_RESOURCE_GROUP not found in environment or configuration.")
        acr_resource_group = input("Please enter your ACR Resource Group name: ").strip()
        if not acr_resource_group:
            print("\nERROR: ACR Resource Group is required.")
            sys.exit(1)
        print()

    print(f"✓ Subscription ID: {subscription_id[:8]}...")
    print(f"✓ ACR Name: {acr_name}")
    print(f"✓ ACR Resource Group: {acr_resource_group}")
    print(f"✓ Image Age Threshold: {IMAGE_AGE_THRESHOLD_DAYS} days")
    print(f"✓ Authentication: Azure CLI")
    print()

    return subscription_id, acr_name, acr_resource_group


def authenticate_azure(subscription_id: str) -> Tuple[AzureCliCredential, ContainerRegistryManagementClient, WebSiteManagementClient]:
    """
    Authenticates with Azure using Azure CLI credentials and creates
    management clients for ACR and App Services.

    Args:
        subscription_id: Azure subscription ID

    Returns:
        Tuple containing credential object, ACR client, and Web client
    """
    print("=" * 80)
    print("AUTHENTICATING WITH AZURE")
    print("=" * 80)

    try:
        # Create credential object using Azure CLI authentication
        # This uses your existing 'az login' session
        credential = AzureCliCredential()

        # Test authentication by creating clients
        acr_client = ContainerRegistryManagementClient(
            credential=credential,
            subscription_id=subscription_id
        )

        web_client = WebSiteManagementClient(
            credential=credential,
            subscription_id=subscription_id
        )

        print("✓ Successfully authenticated with Azure using Azure CLI")
        print(f"✓ Subscription: {subscription_id}")
        print()

        return credential, acr_client, web_client

    except AzureError as e:
        print(f"\nERROR: Authentication failed: {e}")
        print("\nPlease ensure you are logged in with 'az login'.")
        sys.exit(1)


# ============================================================================
# ACR IMAGE DISCOVERY
# ============================================================================

def get_all_acr_manifests(acr_name: str, resource_group: str) -> Dict[str, List[Dict]]:
    """
    Retrieves all repositories and their manifests from the specified ACR.
    Uses Azure CLI for detailed manifest information as the SDK has limitations.

    Args:
        acr_name: Name of the Azure Container Registry
        resource_group: Resource group containing the ACR

    Returns:
        Dictionary mapping repository names to lists of manifest information
    """
    print("=" * 80)
    print("DISCOVERING ACR REPOSITORIES AND MANIFESTS")
    print("=" * 80)

    repositories = {}

    try:
        # Get list of repositories using Azure CLI
        print(f"Fetching repositories from ACR '{acr_name}'...")
        result = subprocess.run(
            ['az.cmd', 'acr', 'repository', 'list', '--name', acr_name],
            capture_output=True,
            text=True,
            check=True
        )

        repo_list = json.loads(result.stdout)
        print(f"✓ Found {len(repo_list)} repositories")
        print()

        # For each repository, get all manifests
        for repo in repo_list:
            print(f"Processing repository: {repo}")

            # Get all manifests for this repository
            manifest_result = subprocess.run(
                ['az.cmd', 'acr', 'repository', 'show-manifests',
                 '--name', acr_name,
                 '--repository', repo,
                 '--detail'],
                capture_output=True,
                text=True,
                check=True
            )

            manifests = json.loads(manifest_result.stdout)

            # Process each manifest
            manifest_list = []
            for manifest in manifests:
                # Extract relevant information
                digest = manifest.get('digest', '').lower()  # Normalize to lowercase
                tags = manifest.get('tags', [])
                created_time_str = manifest.get('createdTime', '')
                size_bytes = manifest.get('imageSize', 0)

                # Parse creation time
                created_time = None
                if created_time_str:
                    try:
                        # Azure returns time in ISO 8601 format
                        created_time = datetime.fromisoformat(created_time_str.replace('Z', '+00:00'))
                    except ValueError:
                        print(f"  Warning: Could not parse time for manifest {digest[:12]}")

                manifest_info = {
                    'digest': digest,
                    'tags': tags if tags else ['<untagged>'],
                    'created_time': created_time,
                    'size_bytes': size_bytes,
                    'repository': repo
                }

                manifest_list.append(manifest_info)

            repositories[repo] = manifest_list
            print(f"  ✓ Found {len(manifest_list)} manifests with {sum(len(m['tags']) for m in manifest_list)} total tags")

        print()
        total_manifests = sum(len(manifests) for manifests in repositories.values())
        print(f"✓ Total manifests discovered: {total_manifests}")
        print()

        return repositories

    except subprocess.CalledProcessError as e:
        print(f"\nERROR: Failed to query ACR: {e}")
        print(f"STDERR: {e.stderr}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"\nERROR: Failed to parse ACR response: {e}")
        sys.exit(1)


def filter_manifests_by_age(repositories: Dict[str, List[Dict]], threshold_days: int) -> Dict[str, List[Dict]]:
    """
    Filters manifests to only include those older than the specified threshold.

    Args:
        repositories: Dictionary of repositories and their manifests
        threshold_days: Age threshold in days

    Returns:
        Filtered dictionary containing only old manifests
    """
    print("=" * 80)
    print(f"FILTERING MANIFESTS OLDER THAN {threshold_days} DAYS")
    print("=" * 80)

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=threshold_days)
    print(f"Cutoff date: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print()

    filtered_repositories = {}
    total_old_manifests = 0

    for repo, manifests in repositories.items():
        old_manifests = []

        for manifest in manifests:
            created_time = manifest.get('created_time')

            if created_time is None:
                print(f"  Warning: Manifest {manifest['digest'][:12]} has no creation time, skipping")
                continue

            if created_time < cutoff_date:
                old_manifests.append(manifest)

        if old_manifests:
            filtered_repositories[repo] = old_manifests
            total_old_manifests += len(old_manifests)
            print(f"Repository '{repo}': {len(old_manifests)} old manifests")

    print()
    print(f"✓ Found {total_old_manifests} manifests older than {threshold_days} days")
    print()

    return filtered_repositories


# ============================================================================
# APP SERVICE IMAGE DETECTION
# ============================================================================

def get_images_in_use_by_app_services(web_client: WebSiteManagementClient,
                                       subscription_id: str,
                                       acr_name: str) -> Tuple[Set[str], Dict[str, List[str]]]:
    """
    Scans all App Services (including deployment slots) in the subscription
    to identify which ACR images are currently in use.

    Args:
        web_client: Azure Web Management Client
        subscription_id: Azure subscription ID
        acr_name: Name of the ACR to filter images

    Returns:
        Tuple of (Set of image references, Dict mapping image references to app service names)
        Image references format: repository@digest or repository:tag
        App service names format: "app-name" for production, "app-name/slot-name" for slots
    """
    print("=" * 80)
    print("SCANNING APP SERVICES FOR IN-USE IMAGES")
    print("=" * 80)

    images_in_use = set()
    image_to_apps = defaultdict(list)  # Maps image reference to list of app services
    acr_login_server = f"{acr_name}.azurecr.io"

    try:
        # Get all App Services in the subscription
        print(f"Fetching all App Services in subscription {subscription_id[:8]}...")
        app_services = list(web_client.web_apps.list())
        print(f"✓ Found {len(app_services)} App Services")
        print()

        # Check each App Service
        for app_service in app_services:
            resource_group = app_service.id.split('/')[4]  # Extract resource group from ARM ID
            app_name = app_service.name

            print(f"Checking App Service: {app_name}")

            # Get configuration for the main (production) slot
            try:
                config = web_client.web_apps.get_configuration(resource_group, app_name)

                # Also get app settings which may contain DOCKER_CUSTOM_IMAGE_NAME
                app_settings = web_client.web_apps.list_application_settings(resource_group, app_name)

                image = extract_acr_image_from_config(config, acr_login_server, app_settings)

                if image:
                    images_in_use.add(image)
                    image_to_apps[image].append(app_name)
                    print(f"  ✓ Production slot uses: {image}")
                else:
                    print(f"  - No ACR image found in production slot")

                # Check all deployment slots
                slots = list(web_client.web_apps.list_slots(resource_group, app_name))

                if slots:
                    print(f"  Checking {len(slots)} deployment slots...")

                    for slot in slots:
                        slot_name = slot.name.split('/')[-1]  # Extract slot name from full name

                        try:
                            slot_config = web_client.web_apps.get_configuration_slot(
                                resource_group, app_name, slot_name
                            )

                            # Get app settings for the slot
                            slot_app_settings = web_client.web_apps.list_application_settings_slot(
                                resource_group, app_name, slot_name
                            )

                            slot_image = extract_acr_image_from_config(slot_config, acr_login_server, slot_app_settings)

                            if slot_image:
                                images_in_use.add(slot_image)
                                slot_full_name = f"{app_name}/{slot_name}"
                                image_to_apps[slot_image].append(slot_full_name)
                                print(f"    ✓ Slot '{slot_name}' uses: {slot_image}")
                            else:
                                print(f"    - Slot '{slot_name}' has no ACR image")

                        except Exception as e:
                            print(f"    Warning: Could not read slot '{slot_name}': {e}")

            except Exception as e:
                print(f"  Warning: Could not read configuration: {e}")

            print()

        print(f"✓ Total unique ACR images in use: {len(images_in_use)}")
        print()

        return images_in_use, dict(image_to_apps)

    except AzureError as e:
        print(f"\nERROR: Failed to scan App Services: {e}")
        sys.exit(1)


def extract_acr_image_from_config(config, acr_login_server: str, app_settings=None) -> str:
    """
    Extracts ACR image reference from App Service configuration.
    Handles both Linux and Windows container configurations.

    Args:
        config: App Service configuration object
        acr_login_server: ACR login server (e.g., myacr.azurecr.io)
        app_settings: App Service application settings (optional)

    Returns:
        Image reference string or empty string if not found
    """
    image = None

    # Debug: Print what we're checking
    print(f"    DEBUG: Checking config for {acr_login_server}")

    # Check for Linux containers
    if hasattr(config, 'linux_fx_version') and config.linux_fx_version:
        print(f"    DEBUG: linux_fx_version = {config.linux_fx_version}")
        # Format is typically "DOCKER|registry.azurecr.io/repo:tag"
        if config.linux_fx_version.startswith('DOCKER|'):
            image = config.linux_fx_version.split('|', 1)[1]

    # Check for Windows containers
    elif hasattr(config, 'windows_fx_version') and config.windows_fx_version:
        print(f"    DEBUG: windows_fx_version = {config.windows_fx_version}")
        if config.windows_fx_version.startswith('DOCKER|'):
            image = config.windows_fx_version.split('|', 1)[1]

    # Check app settings for DOCKER_CUSTOM_IMAGE_NAME
    if not image and app_settings and hasattr(app_settings, 'properties'):
        settings_dict = app_settings.properties
        print(f"    DEBUG: Checking app settings, found {len(settings_dict)} settings")

        # Check for DOCKER_CUSTOM_IMAGE_NAME
        if 'DOCKER_CUSTOM_IMAGE_NAME' in settings_dict:
            image = settings_dict['DOCKER_CUSTOM_IMAGE_NAME']
            print(f"    DEBUG: Found DOCKER_CUSTOM_IMAGE_NAME = {image}")

        # Also check for WEBSITES_CONTAINER_START_TIME_LIMIT and DOCKER_REGISTRY_SERVER_URL
        # which indicate this is a container app
        if 'DOCKER_REGISTRY_SERVER_URL' in settings_dict:
            registry_url = settings_dict['DOCKER_REGISTRY_SERVER_URL']
            print(f"    DEBUG: Found DOCKER_REGISTRY_SERVER_URL = {registry_url}")

    if not image:
        print(f"    DEBUG: No linux_fx_version, windows_fx_version, or DOCKER_CUSTOM_IMAGE_NAME found")

    # Filter to only include images from our ACR (case-insensitive comparison)
    if image and acr_login_server.lower() in image.lower():
        return image
    elif image:
        print(f"    DEBUG: Found image '{image}' but it doesn't match ACR server '{acr_login_server}'")

    return ''


def resolve_images_to_manifests(images_in_use: Set[str], image_to_apps: Dict[str, List[str]], acr_name: str) -> Tuple[Set[str], Dict[str, List[str]]]:
    """
    Converts image references (which may use tags) to manifest digests.
    This ensures we're comparing at the manifest level, not tag level.
    Also maintains the mapping of which app services use which digests.

    Args:
        images_in_use: Set of image references from App Services
        image_to_apps: Dict mapping image references to app service names
        acr_name: Name of the ACR

    Returns:
        Tuple of (Set of manifest digests, Dict mapping digests to app service names)
    """
    print("=" * 80)
    print("RESOLVING IMAGE REFERENCES TO MANIFEST DIGESTS")
    print("=" * 80)

    manifest_digests = set()
    digest_to_apps = defaultdict(list)  # Maps digest to list of app services
    acr_login_server = f"{acr_name}.azurecr.io"

    for image_ref in images_in_use:
        print(f"Resolving: {image_ref}")

        # Remove the ACR server prefix to get repository:tag or repository@digest (case-insensitive)
        if image_ref.lower().startswith(acr_login_server.lower() + '/'):
            # Find the position after the server name and '/' to extract the image part
            prefix_length = len(acr_login_server) + 1
            image_part = image_ref[prefix_length:]
        else:
            image_part = image_ref

        # Check if already a digest reference (repository@sha256:...)
        if '@sha256:' in image_part:
            digest = image_part.split('@')[1].lower()  # Normalize to lowercase
            manifest_digests.add(digest)
            # Map digest to app services
            if image_ref in image_to_apps:
                digest_to_apps[digest].extend(image_to_apps[image_ref])
            print(f"  ✓ Already a digest: {digest[:12]}...")
            continue

        # Otherwise it's a tag reference, need to resolve to digest
        if ':' in image_part:
            repository, tag = image_part.rsplit(':', 1)
        else:
            repository = image_part
            tag = 'latest'

        try:
            # Use Azure CLI to get manifest for this tag
            result = subprocess.run(
                ['az.cmd', 'acr', 'repository', 'show',
                 '--name', acr_name,
                 '--image', f"{repository}:{tag}"],
                capture_output=True,
                text=True,
                check=True
            )

            manifest_info = json.loads(result.stdout)
            digest = manifest_info.get('digest', '')

            if digest:
                digest = digest.lower()  # Normalize to lowercase
                manifest_digests.add(digest)
                # Map digest to app services
                if image_ref in image_to_apps:
                    digest_to_apps[digest].extend(image_to_apps[image_ref])
                print(f"  ✓ Resolved to digest: {digest[:12]}...")
            else:
                print(f"  Warning: Could not resolve to digest")

        except subprocess.CalledProcessError as e:
            print(f"  Warning: Failed to resolve tag '{repository}:{tag}': {e.stderr}")
        except json.JSONDecodeError:
            print(f"  Warning: Failed to parse response for '{repository}:{tag}'")

    print()
    print(f"✓ Resolved {len(manifest_digests)} unique manifest digests in use")
    print()

    return manifest_digests, dict(digest_to_apps)


# ============================================================================
# UNUSED IMAGE IDENTIFICATION
# ============================================================================

def identify_unused_manifests(old_repositories: Dict[str, List[Dict]],
                               manifests_in_use: Set[str],
                               digest_to_apps: Dict[str, List[str]]) -> Tuple[List[Dict], List[Dict]]:
    """
    Compares old manifests against those in use to identify candidates for deletion.
    Also identifies old manifests that are still in use (for warning purposes).

    Args:
        old_repositories: Dictionary of repositories with old manifests
        manifests_in_use: Set of manifest digests currently in use
        digest_to_apps: Dict mapping digests to app service names

    Returns:
        Tuple of (List of unused manifests, List of old manifests in use with app info)
    """
    print("=" * 80)
    print("IDENTIFYING UNUSED MANIFESTS")
    print("=" * 80)

    unused_manifests = []
    old_manifests_in_use = []

    for repo, manifests in old_repositories.items():
        print(f"Analyzing repository: {repo}")

        for manifest in manifests:
            digest = manifest['digest']

            if digest not in manifests_in_use:
                unused_manifests.append(manifest)
                tags_str = ', '.join(manifest['tags'])
                print(f"  ✗ UNUSED: {digest[:12]}... (tags: {tags_str})")
            else:
                # This old manifest is in use - track it for warnings
                manifest_with_apps = manifest.copy()
                manifest_with_apps['used_by_apps'] = digest_to_apps.get(digest, [])
                old_manifests_in_use.append(manifest_with_apps)

                tags_str = ', '.join(manifest['tags'])
                print(f"  ✓ IN USE: {digest[:12]}... (tags: {tags_str})")

        print()

    print(f"✓ Found {len(unused_manifests)} unused manifests eligible for deletion")
    if old_manifests_in_use:
        print(f"⚠ Found {len(old_manifests_in_use)} old manifests still in use by App Services")
    print()

    return unused_manifests, old_manifests_in_use


# ============================================================================
# OLD MANIFESTS IN USE WARNING
# ============================================================================

def display_old_manifests_warning(old_manifests_in_use: List[Dict], threshold_days: int):
    """
    Displays warning-level messages for old manifests that are still in use by App Services.
    Provides metrics and recommendations for updating these manifests.

    Args:
        old_manifests_in_use: List of old manifest dictionaries with app service info
        threshold_days: Age threshold in days
    """
    if not old_manifests_in_use:
        return

    print("=" * 80)
    print("⚠ WARNING: OLD MANIFESTS STILL IN USE BY APP SERVICES")
    print("=" * 80)
    print()
    print(f"The following {len(old_manifests_in_use)} manifest(s) are older than {threshold_days} days")
    print("but are still being used by App Services and will NOT be deleted.")
    print()
    print("RECOMMENDATION: Consider updating these App Services to use newer images.")
    print("=" * 80)
    print()

    # Group by repository for cleaner display
    by_repo = defaultdict(list)
    for manifest in old_manifests_in_use:
        by_repo[manifest['repository']].append(manifest)

    total_size_bytes = 0
    max_age_days = 0

    for repo in sorted(by_repo.keys()):
        print(f"Repository: {repo}")
        print("-" * 80)

        # Sort manifests from oldest to newest
        sorted_manifests = sorted(by_repo[repo], key=lambda m: m['created_time'])

        for manifest in sorted_manifests:
            digest = manifest['digest']
            tags = ', '.join(manifest['tags'])
            created_time = manifest['created_time']
            size_mb = manifest['size_bytes'] / (1024 * 1024)
            total_size_bytes += manifest['size_bytes']
            used_by_apps = manifest.get('used_by_apps', [])

            age_days = (datetime.now(timezone.utc) - created_time).days
            max_age_days = max(max_age_days, age_days)
            days_over_threshold = age_days - threshold_days

            print(f"  Digest:   {digest}")
            print(f"  Tags:     {tags}")
            print(f"  Created:  {created_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            print(f"  Age:      {age_days} days old (⚠ {days_over_threshold} days over threshold)")
            print(f"  Size:     {size_mb:.2f} MB")
            print(f"  Used by:  {len(used_by_apps)} App Service(s)")

            for app in sorted(used_by_apps):
                print(f"            - {app}")

            print()

        print()

    total_size_mb = total_size_bytes / (1024 * 1024)
    total_size_gb = total_size_bytes / (1024 * 1024 * 1024)
    avg_age = sum((datetime.now(timezone.utc) - m['created_time']).days for m in old_manifests_in_use) / len(old_manifests_in_use)

    print("=" * 80)
    print("OLD MANIFESTS IN USE - SUMMARY METRICS")
    print("=" * 80)
    print(f"Total old manifests in use:          {len(old_manifests_in_use)}")
    print(f"Total size of old images:            {total_size_gb:.2f} GB ({total_size_mb:.2f} MB)")
    print(f"Oldest manifest age:                 {max_age_days} days")
    print(f"Average age:                         {avg_age:.1f} days")
    print(f"Threshold exceeded by (oldest):      {max_age_days - threshold_days} days")
    print(f"Total App Services affected:         {len(set(app for m in old_manifests_in_use for app in m.get('used_by_apps', [])))}")
    print("=" * 80)
    print()
    print("RECOMMENDATIONS:")
    print("  1. Review and update App Services to use newer image versions")
    print("  2. Consider implementing automated image update policies")
    print("  3. Set up monitoring/alerts for image age in production environments")
    print("  4. Review the audit log for detailed information on affected services")
    print("=" * 80)
    print()


# ============================================================================
# DELETION (MOCK MODE)
# ============================================================================

def display_unused_manifests_summary(unused_manifests: List[Dict]):
    """
    Displays a formatted summary of unused manifests.

    Args:
        unused_manifests: List of unused manifest dictionaries
    """
    print("=" * 80)
    print("UNUSED MANIFESTS SUMMARY")
    print("=" * 80)
    print()

    if not unused_manifests:
        print("No unused manifests found. Nothing to delete!")
        return

    # Group by repository for cleaner display
    by_repo = defaultdict(list)
    for manifest in unused_manifests:
        by_repo[manifest['repository']].append(manifest)

    total_size_bytes = 0

    for repo in sorted(by_repo.keys()):
        print(f"Repository: {repo}")
        print("-" * 80)

        # Sort manifests from oldest to newest
        sorted_manifests = sorted(by_repo[repo], key=lambda m: m['created_time'])

        for manifest in sorted_manifests:
            digest = manifest['digest']
            tags = ', '.join(manifest['tags'])
            created_time = manifest['created_time']
            size_mb = manifest['size_bytes'] / (1024 * 1024)
            total_size_bytes += manifest['size_bytes']

            age_days = (datetime.now(timezone.utc) - created_time).days

            print(f"  Digest:  {digest}")
            print(f"  Tags:    {tags}")
            print(f"  Created: {created_time.strftime('%Y-%m-%d %H:%M:%S UTC')} ({age_days} days ago)")
            print(f"  Size:    {size_mb:.2f} MB")
            print()

        print()

    total_size_mb = total_size_bytes / (1024 * 1024)
    total_size_gb = total_size_bytes / (1024 * 1024 * 1024)

    print("=" * 80)
    print(f"Total manifests to delete: {len(unused_manifests)}")
    print(f"Total space to reclaim: {total_size_gb:.2f} GB ({total_size_mb:.2f} MB)")
    print("=" * 80)
    print()


def mock_delete_manifests(unused_manifests: List[Dict], acr_name: str):
    """
    Performs a mock deletion of unused manifests by echoing their names.
    This is the safe mode before implementing actual deletion.

    Args:
        unused_manifests: List of unused manifest dictionaries
        acr_name: Name of the ACR
    """
    print("=" * 80)
    print("MOCK DELETION (NO ACTUAL DELETION OCCURS)")
    print("=" * 80)
    print()

    if not unused_manifests:
        print("No manifests to delete.")
        return

    print("The following Azure CLI commands would be executed:")
    print()

    for i, manifest in enumerate(unused_manifests, 1):
        repo = manifest['repository']
        digest = manifest['digest']
        tags = ', '.join(manifest['tags'])

        # The actual command that would be run in production mode
        command = f"az acr repository delete --name {acr_name} --image {repo}@{digest} --yes"

        print(f"[{i}/{len(unused_manifests)}] {command}")
        print(f"         (Would delete: {repo}@{digest[:12]}... with tags: {tags})")
        print()

    print("=" * 80)
    print("MOCK DELETION COMPLETE - No images were actually deleted")
    print("=" * 80)


def hard_delete_manifests(unused_manifests: List[Dict], acr_name: str) -> Optional[Dict]:
    """
    Performs actual deletion of unused manifests from ACR.
    WARNING: This permanently deletes container images!

    Args:
        unused_manifests: List of unused manifest dictionaries
        acr_name: Name of the ACR

    Returns:
        Dictionary mapping digest to deletion result, or None if cancelled
    """
    print("=" * 80)
    print("HARD DELETION MODE - IMAGES WILL BE PERMANENTLY DELETED!")
    print("=" * 80)
    print()

    if not unused_manifests:
        print("No manifests to delete.")
        return None

    print(f"WARNING: You are about to permanently delete {len(unused_manifests)} manifest(s)!")
    print("This action CANNOT be undone.")
    print()

    # Final confirmation
    response = input("Type 'DELETE' (in all caps) to confirm deletion: ").strip()

    if response != 'DELETE':
        print("\nDeletion cancelled. No images were deleted.")
        return None

    print()
    print("=" * 80)
    print("BEGINNING DELETION PROCESS")
    print("=" * 80)
    print()

    deleted_count = 0
    failed_count = 0
    failed_deletions = []
    deletion_results = {}  # Track results for audit

    for i, manifest in enumerate(unused_manifests, 1):
        repo = manifest['repository']
        digest = manifest['digest']
        tags = ', '.join(manifest['tags'])

        print(f"[{i}/{len(unused_manifests)}] Deleting {repo}@{digest[:12]}... (tags: {tags})")

        try:
            # Execute the actual deletion command
            result = subprocess.run(
                ['az.cmd', 'acr', 'repository', 'delete',
                 '--name', acr_name,
                 '--image', f"{repo}@{digest}",
                 '--yes'],
                capture_output=True,
                text=True,
                check=True,
                timeout=60  # 60 second timeout per deletion
            )

            print(f"  ✓ Successfully deleted {repo}@{digest[:12]}...")
            deleted_count += 1
            deletion_results[digest] = {
                'status': 'success',
                'repository': repo,
                'tags': tags,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else str(e)
            print(f"  ✗ FAILED to delete {repo}@{digest[:12]}...")
            print(f"     Error: {error_msg}")
            failed_count += 1
            failed_deletions.append({
                'repository': repo,
                'digest': digest,
                'tags': tags,
                'error': error_msg
            })
            deletion_results[digest] = {
                'status': 'failed',
                'repository': repo,
                'tags': tags,
                'error': error_msg,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

        except subprocess.TimeoutExpired:
            error_msg = 'Deletion command timed out after 60 seconds'
            print(f"  ✗ TIMEOUT deleting {repo}@{digest[:12]}...")
            failed_count += 1
            failed_deletions.append({
                'repository': repo,
                'digest': digest,
                'tags': tags,
                'error': error_msg
            })
            deletion_results[digest] = {
                'status': 'failed',
                'repository': repo,
                'tags': tags,
                'error': error_msg,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

        print()

    # Summary
    print("=" * 80)
    print("DELETION COMPLETE")
    print("=" * 80)
    print(f"Successfully deleted: {deleted_count}/{len(unused_manifests)} manifests")

    if failed_count > 0:
        print(f"Failed deletions: {failed_count}/{len(unused_manifests)} manifests")
        print()
        print("Failed deletions details:")
        for failure in failed_deletions:
            print(f"  - {failure['repository']}@{failure['digest'][:12]}...")
            print(f"    Tags: {failure['tags']}")
            print(f"    Error: {failure['error']}")
            print()

    print("=" * 80)

    return deletion_results


def select_deletion_mode() -> str:
    """
    Prompts the user to select between mock deletion and hard deletion modes.

    Returns:
        'mock' or 'hard' based on user selection
    """
    print()
    print("=" * 80)
    print("DELETION MODE SELECTION")
    print("=" * 80)
    print()
    print("Please select a deletion mode:")
    print()
    print("  1. MOCK MODE (Safe) - Show what would be deleted without making changes")
    print("  2. HARD DELETE MODE (Dangerous) - Permanently delete images from ACR")
    print()

    while True:
        choice = input("Enter your choice (1 or 2): ").strip()

        if choice == '1':
            print()
            print("✓ Mock mode selected - No images will be deleted")
            print()
            return 'mock'
        elif choice == '2':
            print()
            print("⚠ WARNING: Hard delete mode selected!")
            print("⚠ This will PERMANENTLY delete images from your ACR!")
            print()
            confirm = input("Are you absolutely sure? Type 'yes' to confirm: ").strip().lower()
            if confirm == 'yes':
                print()
                print("✓ Hard delete mode confirmed")
                print()
                return 'hard'
            else:
                print()
                print("Hard delete cancelled. Returning to mode selection...")
                print()
        else:
            print("Invalid choice. Please enter 1 or 2.")


def get_system_info() -> Dict:
    """
    Gathers system information for audit trail.

    Returns:
        Dictionary containing system information
    """
    system_info = {
        'hostname': socket.gethostname(),
        'platform': platform.platform(),
        'python_version': platform.python_version(),
        'user': getpass.getuser(),
        'os_type': platform.system(),
        'os_version': platform.version()
    }

    # Try to get Azure CLI version
    try:
        result = subprocess.run(
            ['az.cmd', '--version'],
            capture_output=True,
            text=True,
            timeout=10
        )
        # Extract just the first line which contains the version
        az_version = result.stdout.split('\n')[0] if result.stdout else 'Unknown'
        system_info['azure_cli_version'] = az_version.strip()
    except Exception:
        system_info['azure_cli_version'] = 'Unable to determine'

    return system_info


def write_audit_log(
    deletion_mode: str,
    subscription_id: str,
    acr_name: str,
    acr_resource_group: str,
    start_time: datetime,
    end_time: datetime,
    unused_manifests: List[Dict],
    old_manifests_in_use: List[Dict],
    deletion_results: Optional[Dict] = None,
    images_in_use_count: int = 0,
    total_manifests_scanned: int = 0,
    old_manifests_count: int = 0
) -> str:
    """
    Writes comprehensive audit log to JSON file.

    Args:
        deletion_mode: 'mock' or 'hard'
        subscription_id: Azure subscription ID
        acr_name: ACR name
        acr_resource_group: ACR resource group
        start_time: Script start time
        end_time: Script end time
        unused_manifests: List of unused manifest dictionaries
        old_manifests_in_use: List of old manifests still in use with app service info
        deletion_results: Results from hard delete (if applicable)
        images_in_use_count: Number of images found in use
        total_manifests_scanned: Total number of manifests scanned
        old_manifests_count: Number of manifests older than threshold

    Returns:
        Path to the audit file created
    """
    # Create audit directory if it doesn't exist
    AUDIT_DIR.mkdir(exist_ok=True)

    # Calculate duration
    duration_seconds = (end_time - start_time).total_seconds()

    # Generate filename with timestamp and relevant info
    timestamp = start_time.strftime('%Y%m%d_%H%M%S')
    manifest_count = len(unused_manifests)
    filename = f"{timestamp}_{deletion_mode}_{acr_name}_{manifest_count}_manifests.json"
    filepath = AUDIT_DIR / filename

    # Build audit data structure
    audit_data = {
        'audit_metadata': {
            'audit_file_version': '1.0',
            'script_version': SCRIPT_VERSION,
            'generated_at': datetime.now(timezone.utc).isoformat(),
        },
        'execution_info': {
            'deletion_mode': deletion_mode,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_seconds': round(duration_seconds, 2),
            'duration_human': f"{int(duration_seconds // 60)}m {int(duration_seconds % 60)}s",
            'executed_by': getpass.getuser(),
        },
        'configuration': {
            'subscription_id': subscription_id,
            'acr_name': acr_name,
            'acr_resource_group': acr_resource_group,
            'image_age_threshold_days': IMAGE_AGE_THRESHOLD_DAYS,
        },
        'system_info': get_system_info(),
        'summary': {
            'total_manifests_scanned': total_manifests_scanned,
            'manifests_older_than_threshold': old_manifests_count,
            'images_in_use': images_in_use_count,
            'unused_manifests_identified': manifest_count,
            'old_manifests_still_in_use': len(old_manifests_in_use),
            'old_manifests_still_in_use_warning': 'These manifests are older than threshold but protected from deletion' if old_manifests_in_use else None,
        },
        'manifests': [],
        'old_manifests_in_use': []
    }

    # Sort manifests by creation time (oldest to newest) regardless of repository
    sorted_manifests = sorted(
        unused_manifests,
        key=lambda m: m['created_time'] if m['created_time'] else datetime.min.replace(tzinfo=timezone.utc)
    )

    # Add detailed manifest information
    for manifest in sorted_manifests:
        manifest_data = {
            'repository': manifest['repository'],
            'digest': manifest['digest'],
            'tags': manifest['tags'],
            'created_time': manifest['created_time'].isoformat() if manifest['created_time'] else None,
            'age_days': (datetime.now(timezone.utc) - manifest['created_time']).days if manifest['created_time'] else None,
            'size_bytes': manifest['size_bytes'],
            'size_mb': round(manifest['size_bytes'] / (1024 * 1024), 2),
        }

        # Add deletion result if this was a hard delete
        if deletion_results and manifest['digest'] in deletion_results:
            manifest_data['deletion_result'] = deletion_results[manifest['digest']]

        audit_data['manifests'].append(manifest_data)

    # Add old manifests in use information
    if old_manifests_in_use:
        # Sort by age (oldest first)
        sorted_old_manifests = sorted(
            old_manifests_in_use,
            key=lambda m: m['created_time'] if m['created_time'] else datetime.min.replace(tzinfo=timezone.utc)
        )

        for manifest in sorted_old_manifests:
            old_manifest_data = {
                'repository': manifest['repository'],
                'digest': manifest['digest'],
                'tags': manifest['tags'],
                'created_time': manifest['created_time'].isoformat() if manifest['created_time'] else None,
                'age_days': (datetime.now(timezone.utc) - manifest['created_time']).days if manifest['created_time'] else None,
                'days_over_threshold': ((datetime.now(timezone.utc) - manifest['created_time']).days - IMAGE_AGE_THRESHOLD_DAYS) if manifest['created_time'] else None,
                'size_bytes': manifest['size_bytes'],
                'size_mb': round(manifest['size_bytes'] / (1024 * 1024), 2),
                'used_by_app_services': manifest.get('used_by_apps', []),
                'app_service_count': len(manifest.get('used_by_apps', [])),
                'status': 'protected_from_deletion',
                'warning': f'This manifest is {(datetime.now(timezone.utc) - manifest["created_time"]).days} days old, exceeding the {IMAGE_AGE_THRESHOLD_DAYS}-day threshold'
            }

            audit_data['old_manifests_in_use'].append(old_manifest_data)

    # Add deletion summary for hard delete mode
    if deletion_mode == 'hard' and deletion_results:
        successful = sum(1 for r in deletion_results.values() if r['status'] == 'success')
        failed = sum(1 for r in deletion_results.values() if r['status'] == 'failed')

        audit_data['deletion_summary'] = {
            'total_attempted': len(deletion_results),
            'successful': successful,
            'failed': failed,
            'success_rate': round((successful / len(deletion_results) * 100), 2) if deletion_results else 0,
        }

        # Add failed deletions details
        if failed > 0:
            audit_data['failed_deletions'] = [
                {
                    'digest': digest,
                    'error': result['error']
                }
                for digest, result in deletion_results.items()
                if result['status'] == 'failed'
            ]

    # Write to file
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(audit_data, f, indent=2, ensure_ascii=False)

    return str(filepath)


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """
    Main execution flow for the ACR image cleanup script.
    """
    # Track execution start time
    start_time = datetime.now(timezone.utc)

    print()
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 15 + "AZURE CONTAINER REGISTRY CLEANUP TOOL" + " " * 26 + "║")
    print("╚" + "=" * 78 + "╝")
    print()

    # Step 1: Validate configuration and get runtime values
    subscription_id, acr_name, acr_resource_group = validate_configuration()

    # Step 2: Authenticate with Azure
    credential, acr_client, web_client = authenticate_azure(subscription_id)

    # Step 3: Discover all ACR manifests
    all_repositories = get_all_acr_manifests(acr_name, acr_resource_group)

    # Calculate total manifests scanned
    total_manifests_scanned = sum(len(manifests) for manifests in all_repositories.values())

    # Step 4: Filter manifests by age
    old_repositories = filter_manifests_by_age(all_repositories, IMAGE_AGE_THRESHOLD_DAYS)

    # Calculate old manifests count
    old_manifests_count = sum(len(manifests) for manifests in old_repositories.values())

    if not old_repositories:
        print("No manifests found older than the threshold. Exiting.")
        return

    # Step 5: Scan App Services to find images in use
    images_in_use, image_to_apps = get_images_in_use_by_app_services(web_client, subscription_id, acr_name)

    # Step 6: Resolve image references to manifest digests
    manifests_in_use, digest_to_apps = resolve_images_to_manifests(images_in_use, image_to_apps, acr_name)

    # Step 7: Identify unused manifests and old manifests still in use
    unused_manifests, old_manifests_in_use = identify_unused_manifests(old_repositories, manifests_in_use, digest_to_apps)

    # Step 8: Display summary
    display_unused_manifests_summary(unused_manifests)

    # Step 9: Display warnings for old manifests still in use
    display_old_manifests_warning(old_manifests_in_use, IMAGE_AGE_THRESHOLD_DAYS)

    # Step 10: Select deletion mode and execute
    deletion_mode = None
    deletion_results = None

    if unused_manifests:
        try:
            deletion_mode = select_deletion_mode()

            if deletion_mode == 'mock':
                mock_delete_manifests(unused_manifests, acr_name)
            elif deletion_mode == 'hard':
                deletion_results = hard_delete_manifests(unused_manifests, acr_name)

        except KeyboardInterrupt:
            print("\n\nOperation cancelled by user.")
            sys.exit(0)

    # Track execution end time
    end_time = datetime.now(timezone.utc)

    # Write audit log if deletion mode was executed
    if deletion_mode and (unused_manifests or old_manifests_in_use):
        try:
            audit_file = write_audit_log(
                deletion_mode=deletion_mode,
                subscription_id=subscription_id,
                acr_name=acr_name,
                acr_resource_group=acr_resource_group,
                start_time=start_time,
                end_time=end_time,
                unused_manifests=unused_manifests,
                old_manifests_in_use=old_manifests_in_use,
                deletion_results=deletion_results,
                images_in_use_count=len(images_in_use),
                total_manifests_scanned=total_manifests_scanned,
                old_manifests_count=old_manifests_count
            )
            print()
            print("=" * 80)
            print(f"✓ Audit log written to: {audit_file}")
            print("=" * 80)
        except Exception as e:
            print()
            print("=" * 80)
            print(f"⚠ Warning: Failed to write audit log: {e}")
            print("=" * 80)

    print()
    print("=" * 80)
    print("SCRIPT EXECUTION COMPLETE")
    print("=" * 80)
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nScript interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
