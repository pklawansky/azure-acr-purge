# Azure Container Registry Image Cleanup Tool

A Python script to automate the cleanup of unused container images in Azure Container Registry (ACR). The script identifies images that are not currently used by any App Service (including deployment slots) and provides options for safe mock deletion or permanent hard deletion.

## Quick Start

1. Ensure you're logged into Azure CLI: `az login`
2. Run the script: `python acr_image_cleanup.py`
3. Enter your Subscription ID, ACR Name, and Resource Group when prompted
4. Select mock mode (option 1) to see what would be deleted
5. Re-run with hard delete mode (option 2) when ready to actually delete images

That's it! No configuration files or environment variables required.

## Features

- **Interactive and user-friendly**: Prompts for configuration and deletion mode - no need to edit code or set environment variables
- **Manifest-level comparison**: Works with actual image digests, not just tags
- **Age-based filtering**: Only considers images older than 30 days for safety
- **Comprehensive scanning**: Checks all App Services and their deployment slots
- **Azure CLI authentication**: Simple authentication using your existing Azure CLI login
- **Case-insensitive matching**: Handles registry name and digest case variations
- **Windows compatible**: Full support for Windows environments
- **Dual deletion modes** (selected at runtime):
  - **Mock mode**: Shows what would be deleted without making changes
  - **Hard delete mode**: Permanently deletes unused images (requires explicit confirmation)
- **Multiple safety confirmations**: Hard delete requires typing 'yes' and 'DELETE' to confirm
- **Comprehensive audit logging**: Automatically creates detailed JSON audit logs for every execution
- **Detailed reporting**: Clear, readable output showing all discovered and unused images
- **Error handling**: Comprehensive error tracking and reporting for deletion operations

## Prerequisites

- Python 3.7 or higher
- Azure CLI installed and configured
- An active Azure CLI login session (`az login`)
- An Azure subscription with:
  - Azure Container Registry (ACR)
  - App Services using container images from the ACR
- Appropriate Azure permissions:
  - **Reader** role on the subscription (to list App Services)
  - **Contributor** role on the ACR (to delete images)

## Installation

1. **Clone or download this repository** to your local machine

2. **Install required Python packages**:
```bash
pip install -r requirements.txt
```

Or install packages directly:
```bash
pip install azure-identity azure-mgmt-containerregistry azure-mgmt-web
```

3. **Verify Azure CLI is installed**:
```bash
az --version
```

If not installed, download from: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli

## Azure Setup

### Authentication

This script uses Azure CLI authentication, which is simpler and more secure than managing service principal credentials.

1. **Login to Azure CLI**:
```bash
az login
```

This will open a browser window for authentication. Login with your Azure credentials.

2. **Set the correct subscription** (if you have multiple):
```bash
az account list --output table
az account set --subscription "<subscription-id-or-name>"
```

3. **Verify your current context**:
```bash
az account show
```

That's it! The script will use your Azure CLI session for all authentication.

## Configuration

You can configure the script in three ways (in order of preference):

### Option 1: Interactive Prompts (Easiest)

Simply run the script and it will prompt you for any missing configuration values. No setup needed!

### Option 2: Environment Variables

Set the following environment variables to avoid being prompted:

**Linux/macOS:**
```bash
export AZURE_SUBSCRIPTION_ID='your-subscription-id'
export AZURE_ACR_NAME='your-acr-name'
export AZURE_ACR_RESOURCE_GROUP='your-resource-group'
```

**Windows (PowerShell):**
```powershell
$env:AZURE_SUBSCRIPTION_ID='your-subscription-id'
$env:AZURE_ACR_NAME='your-acr-name'
$env:AZURE_ACR_RESOURCE_GROUP='your-resource-group'
```

**Windows (Command Prompt):**
```cmd
set AZURE_SUBSCRIPTION_ID=your-subscription-id
set AZURE_ACR_NAME=your-acr-name
set AZURE_ACR_RESOURCE_GROUP=your-resource-group
```

### Option 3: Edit the Script

Edit `acr_image_cleanup.py` and set default values in the configuration section:

```python
SUBSCRIPTION_ID = os.getenv('AZURE_SUBSCRIPTION_ID', 'your-subscription-id')
ACR_NAME = os.getenv('AZURE_ACR_NAME', 'your-acr-name')
ACR_RESOURCE_GROUP = os.getenv('AZURE_ACR_RESOURCE_GROUP', 'your-resource-group')
IMAGE_AGE_THRESHOLD_DAYS = 30  # Adjust as needed
```

## Usage

### Running the Script

**Basic usage:**
```bash
python acr_image_cleanup.py
```

**On Windows, you may need:**
```cmd
python acr_image_cleanup.py
```

### Interactive Prompts

The script will interactively prompt you for:

1. **Configuration values** (if not set in environment variables or script):
   - Azure Subscription ID
   - ACR Name
   - ACR Resource Group

   Example:
   ```
   ================================================================================
   VALIDATING CONFIGURATION
   ================================================================================

   AZURE_SUBSCRIPTION_ID not found in environment or configuration.
   Please enter your Azure Subscription ID: 2d267a12-91d5-4858-9031-716ebb3394d8

   AZURE_ACR_NAME not found in environment or configuration.
   Please enter your Azure Container Registry name: MyContainerRegistry

   AZURE_ACR_RESOURCE_GROUP not found in environment or configuration.
   Please enter your ACR Resource Group name: MyResourceGroup
   ```

2. **Deletion mode selection** (always prompted):
   - Option 1: Mock mode (safe - shows what would be deleted)
   - Option 2: Hard delete mode (dangerous - actually deletes images)

   Example:
   ```
   ================================================================================
   DELETION MODE SELECTION
   ================================================================================

   Please select a deletion mode:

     1. MOCK MODE (Safe) - Show what would be deleted without making changes
     2. HARD DELETE MODE (Dangerous) - Permanently delete images from ACR

   Enter your choice (1 or 2):
   ```

This makes the script easy to use without needing to set environment variables or edit the script.

### What the Script Does

1. **Prompts for configuration** - Requests any missing configuration values (Subscription ID, ACR Name, Resource Group)
2. **Validates configuration** - Ensures all required settings are provided
3. **Authenticates with Azure** - Uses your Azure CLI credentials
4. **Discovers ACR repositories** - Lists all repositories in your ACR
5. **Fetches all manifests** - Gets detailed information for each image
6. **Filters by age** - Only considers images older than 30 days
7. **Scans App Services** - Checks which images are currently deployed to production and all slots
8. **Checks deployment slots** - Includes staging and other non-production slots
9. **Resolves references** - Converts tags to manifest digests for accurate comparison
10. **Identifies unused images** - Compares old images against those in use
11. **Displays summary** - Shows detailed information about unused images (sorted oldest to newest)
12. **Prompts for deletion mode** - Asks whether to use mock mode or hard delete mode
13. **Executes deletion** - Runs the selected deletion mode with appropriate confirmations

### Example Output

```
╔==============================================================================╗
║               AZURE CONTAINER REGISTRY CLEANUP TOOL                          ║
╚==============================================================================╝

================================================================================
VALIDATING CONFIGURATION
================================================================================

✓ Subscription ID: 2d267a12...
✓ ACR Name: MyContainerRegistry
✓ ACR Resource Group: MyResourceGroup
✓ Image Age Threshold: 30 days
✓ Authentication: Azure CLI

================================================================================
AUTHENTICATING WITH AZURE
================================================================================
✓ Successfully authenticated with Azure using Azure CLI
✓ Subscription: 2d267a12...

... [manifest discovery and scanning output] ...

================================================================================
UNUSED MANIFESTS SUMMARY
================================================================================

Repository: myapp/frontend
--------------------------------------------------------------------------------
  Digest:  sha256:abc123def456...
  Tags:    v1.2.0, build-789
  Created: 2024-01-15 10:30:00 UTC (45 days ago)
  Size:    125.50 MB

  Digest:  sha256:def456ghi789...
  Tags:    v1.1.0
  Created: 2024-01-10 14:20:00 UTC (50 days ago)
  Size:    123.20 MB

================================================================================
Total manifests to delete: 2
Total space to reclaim: 0.24 GB (248.70 MB)
================================================================================

================================================================================
DELETION MODE SELECTION
================================================================================

Please select a deletion mode:

  1. MOCK MODE (Safe) - Show what would be deleted without making changes
  2. HARD DELETE MODE (Dangerous) - Permanently delete images from ACR

Enter your choice (1 or 2): 1

✓ Mock mode selected - No images will be deleted

================================================================================
MOCK DELETION (NO ACTUAL DELETION OCCURS)
================================================================================

The following Azure CLI commands would be executed:

[1/2] az acr repository delete --name MyContainerRegistry --image myapp/frontend@sha256:abc123def456... --yes
         (Would delete: myapp/frontend@sha256:abc123... with tags: v1.2.0, build-789)

[2/2] az acr repository delete --name MyContainerRegistry --image myapp/frontend@sha256:def456ghi789... --yes
         (Would delete: myapp/frontend@sha256:def456... with tags: v1.1.0)

================================================================================
MOCK DELETION COMPLETE - No images were actually deleted
================================================================================

================================================================================
✓ Audit log written to: audits/20250114_153045_mock_MyContainerRegistry_2_manifests.json
================================================================================
```

## Audit Logging

The script automatically creates comprehensive audit logs in JSON format for every execution where deletion mode is selected (mock or hard delete).

### Audit File Location

Audit logs are saved in the `audits/` subdirectory in the same location where you run the script.

### Audit File Naming

Files are named with the format:
```
{timestamp}_{mode}_{acr_name}_{count}_manifests.json
```

Example: `20250114_153045_mock_MyContainerRegistry_15_manifests.json`

This tells you:
- When it ran: `20250114_153045` (January 14, 2025 at 15:30:45)
- What mode: `mock` or `hard`
- Which ACR: `MyContainerRegistry`
- How many manifests: `15`

### Audit File Contents

Each audit file includes:

**Audit Metadata:**
- Audit file version
- Script version
- Timestamp when file was generated

**Execution Information:**
- Deletion mode (mock or hard)
- Start and end timestamps
- Execution duration (in seconds and human-readable format)
- User who executed the script

**Configuration:**
- Azure subscription ID
- ACR name and resource group
- Image age threshold used

**System Information:**
- Hostname
- Operating system and version
- Python version
- Azure CLI version
- User account

**Summary Statistics:**
- Total manifests scanned
- Manifests older than threshold
- Images currently in use
- Unused manifests identified

**Detailed Manifest Information:**
For each manifest identified for deletion:
- Repository name
- Full digest
- Tags
- Creation timestamp
- Age in days
- Size in bytes and MB

**Deletion Results (Hard Delete Only):**
- Total attempted deletions
- Successful count
- Failed count
- Success rate percentage
- Detailed error messages for any failures
- Timestamp for each deletion attempt

### Example Audit File Structure

```json
{
  "audit_metadata": {
    "audit_file_version": "1.0",
    "script_version": "1.0.0",
    "generated_at": "2025-01-14T15:30:45.123456+00:00"
  },
  "execution_info": {
    "deletion_mode": "mock",
    "start_time": "2025-01-14T15:28:12.000000+00:00",
    "end_time": "2025-01-14T15:30:45.000000+00:00",
    "duration_seconds": 153.5,
    "duration_human": "2m 33s",
    "executed_by": "john.doe"
  },
  "configuration": {
    "subscription_id": "2d267a12-91d5-4858-9031-716ebb3394d8",
    "acr_name": "MyContainerRegistry",
    "acr_resource_group": "MyResourceGroup",
    "image_age_threshold_days": 30
  },
  "system_info": {
    "hostname": "DESKTOP-ABC123",
    "platform": "Windows-10-10.0.19041-SP0",
    "python_version": "3.11.0",
    "user": "john.doe",
    "os_type": "Windows",
    "azure_cli_version": "azure-cli 2.55.0"
  },
  "summary": {
    "total_manifests_scanned": 245,
    "manifests_older_than_threshold": 82,
    "images_in_use": 67,
    "unused_manifests_identified": 15
  },
  "manifests": [
    {
      "repository": "myapp/frontend",
      "digest": "sha256:abc123...",
      "tags": ["v1.2.0", "build-789"],
      "created_time": "2024-01-15T10:30:00+00:00",
      "age_days": 45,
      "size_bytes": 131621888,
      "size_mb": 125.5
    }
  ],
  "deletion_summary": {
    "total_attempted": 15,
    "successful": 14,
    "failed": 1,
    "success_rate": 93.33
  },
  "failed_deletions": [
    {
      "digest": "sha256:xyz789...",
      "error": "Image is locked or in use"
    }
  ]
}
```

### Benefits of Audit Logging

1. **Compliance**: Maintain records of all cleanup operations for audit and compliance requirements
2. **Accountability**: Track who executed deletions and when
3. **Troubleshooting**: Detailed error logs help diagnose issues
4. **Analysis**: Review patterns in image usage and cleanup over time
5. **Rollback Planning**: Have complete records to help rebuild images if needed
6. **Reporting**: Easy to parse JSON format for generating reports

### Using Audit Logs

- **Review before hard delete**: Compare audit logs from mock runs to verify correctness
- **Track cleanup history**: Keep audit files to monitor ACR cleanup patterns over time
- **Generate reports**: Parse JSON files to create summary reports for management
- **Incident response**: Use audit trails to investigate unexpected deletions
- **Automation integration**: Incorporate audit files into your monitoring and alerting systems

### Security Considerations

The audit files contain sensitive information including:
- Azure subscription IDs
- ACR names and resource groups
- System information (hostname, usernames)

**Important**:
- The `audits/` folder is automatically excluded from git via `.gitignore`
- Store audit files securely if they contain sensitive information
- Consider encrypting audit files if storing long-term
- Restrict access to audit files to authorized personnel only

## Safety Features

- **Age threshold**: Only images older than 30 days are considered
- **In-use protection**: Images currently deployed to any App Service are never deleted
- **Slot checking**: All deployment slots are checked to prevent deleting images in staging/preview
- **Case-insensitive matching**: Handles variations in ACR registry name casing
- **Interactive mode selection**: User must explicitly choose between mock and hard delete modes
- **Mock mode option**: Safe mode available to preview deletions without making any changes
- **Multiple confirmation prompts**:
  - User must select deletion mode each run
  - Hard delete mode requires typing 'yes' to confirm mode selection
  - Hard delete mode requires typing 'DELETE' in all caps before executing
- **Comprehensive audit trail**: Every execution creates a detailed JSON audit log with full traceability
- **Error tracking**: Failed deletions are tracked and reported separately with detailed error messages
- **Digest-level comparison**: Works with manifest digests, not just tags, for accurate tracking
- **Keyboard interrupt handling**: Can cancel operation at any time with Ctrl+C

## Customization

### Configurable Parameters

You can modify these values in the script (`acr_image_cleanup.py`):

- `IMAGE_AGE_THRESHOLD_DAYS`: Change the age threshold (default: 30 days)
  ```python
  IMAGE_AGE_THRESHOLD_DAYS = 30  # Change to your preferred threshold
  ```

### Deletion Modes

The script supports two deletion modes, which you select interactively when you run the script:

1. **Mock Mode (Option 1)**:
   - Shows what would be deleted without making any changes
   - Safe for testing and validation
   - Displays the exact Azure CLI commands that would be executed

2. **Hard Delete Mode (Option 2)**:
   - Actually deletes images from your ACR
   - Requires multiple confirmations:
     - First: Confirm mode selection by typing 'yes'
     - Second: Confirm deletion by typing 'DELETE' in all caps
   - Provides detailed feedback on success/failure for each deletion
   - **Warning**: This permanently deletes images and cannot be undone!

**Best Practice**: Always run in mock mode first to verify the correct images will be deleted, then re-run in hard delete mode when ready.

### Future Enhancements

Potential additions for future versions:
- Support for Azure Kubernetes Service (AKS) image checking
- Support for Azure Container Instances
- Logging to file for audit purposes
- Export deletion reports to CSV or JSON
- Batch processing with configurable batch sizes
- Notification integration (email, Teams, Slack)

## Troubleshooting

### "Missing required configuration values" or Empty Input Prompts
- The script will automatically prompt for missing values at runtime
- If you see this error, it means you entered an empty value when prompted
- Simply re-run the script and enter the required values when prompted
- Alternatively, set environment variables or edit the script to avoid prompts

### "Authentication failed" or "Please ensure you are logged in with 'az login'"
- Run `az login` to authenticate with Azure
- Verify you're logged in: `az account show`
- Ensure you have the correct subscription selected: `az account set --subscription <id>`
- Check that your account has appropriate permissions

### "FileNotFoundError: [WinError 2] The system cannot find the file specified"
- **Windows users**: Ensure Azure CLI is installed and in your PATH
- Try running `az --version` in Command Prompt or PowerShell
- The script uses `az.cmd` for Windows compatibility
- Restart your terminal after installing Azure CLI

### "Failed to query ACR" or repository commands fail
- Verify Azure CLI is installed and in PATH: `az --version`
- Ensure the ACR name and resource group are correct
- Check that your account has access to the ACR
- Try running `az acr repository list --name <your-acr-name>` manually

### "Failed to scan App Services"
- Verify the subscription ID is correct
- Ensure your account has Reader permissions on the subscription
- Check that App Services exist in the subscription

### No images detected as "in use" but they should be
- Check that the ACR registry name casing matches (the script handles this, but verify configuration)
- Ensure App Services are actually using images from the specified ACR
- Verify images are configured in App Service settings (linux_fx_version or app settings)
- Check debug output for image discovery issues

### Images marked as "in use" are still shown as unused
- Verify the digest comparison is working (check for case sensitivity issues)
- Ensure the tag-to-digest resolution is successful
- Check that the manifest age filter isn't excluding in-use images

## Workflow

Here's the recommended workflow for using this script:

1. **First run**: Use mock mode to see what would be deleted
   ```bash
   python acr_image_cleanup.py
   # Select Option 1 (Mock Mode) when prompted
   ```

2. **Review the output**: Carefully examine the unused manifests identified
   - Check the repository names
   - Verify the tags
   - Confirm the ages are accurate
   - Ensure no critical images are marked for deletion

3. **Verify accuracy**: Manually confirm some of the images marked as unused are truly not in use

4. **Test in non-production**: Run the script against a test or development ACR first if possible

5. **Second run - Hard delete**: When confident, run again with hard delete mode
   ```bash
   python acr_image_cleanup.py
   # Select Option 2 (Hard Delete Mode) when prompted
   # Confirm with 'yes'
   # Confirm again by typing 'DELETE'
   ```

6. **Monitor results**:
   - Check the deletion summary for any failures
   - Verify services remain operational
   - Confirm ACR storage usage decreases

7. **Schedule regular runs**: Consider running this script monthly or quarterly to keep your ACR clean

## Important Notes

- **Backup considerations**: ACR doesn't have a built-in "undo" for deletions. Ensure you can rebuild any deleted images if needed.
- **CI/CD impact**: Deleted tags won't affect running services, but may impact rollback capabilities.
- **Storage reclaim**: Deleted images free up storage space, but Azure may take time to recalculate usage.
- **Audit trail**: Consider logging all deletions for compliance and troubleshooting purposes.

## Tips and Best Practices

### Running the Script Effectively

1. **Always start with mock mode**: Run in mock mode first to preview what will be deleted
2. **Review the output carefully**: Check repository names, tags, and creation dates before proceeding
3. **Check the audit log**: Review the JSON audit file from mock mode before proceeding to hard delete
4. **Test in non-production first**: If possible, test on a dev/test ACR before running on production
5. **Save the audit files**: Keep audit logs for compliance and troubleshooting purposes
6. **Run during maintenance windows**: Schedule deletions during low-traffic periods

### Configuration Tips

1. **Use environment variables for automation**: Set environment variables if running as part of automation
2. **Edit the script for repeated use**: If you always use the same ACR, hardcode the values in the script
3. **Keep age threshold conservative**: The default 30 days is safe; increase if you need longer retention

### Deletion Best Practices

1. **Start with a small age threshold**: Test with 60 or 90 days first, then lower to 30 days
2. **Don't rush the hard delete**: Give yourself time to review the mock output and audit log
3. **Compare audit logs**: Review the mock mode audit file before running hard delete
4. **Monitor after deletion**: Check that all services remain healthy after deletion
5. **Archive audit logs**: Keep audit files in a secure location for compliance and future reference
6. **Review patterns**: Periodically analyze audit logs to identify trends in image usage

### Automation Ideas

1. **Schedule monthly cleanups**: Add to your maintenance schedule
2. **Create alerts**: Monitor ACR storage usage and run cleanup when it gets high
3. **Integrate with CI/CD**: Consider running cleanup as part of your deployment pipeline
4. **Export reports**: Redirect output to a file for recordkeeping: `python acr_image_cleanup.py > cleanup-report.txt`

## License

This script is provided as-is for use in managing Azure Container Registry resources.

## Support

For issues related to:
- Azure services: Consult Azure documentation or support
- This script: Review the inline comments and error messages
