# First-scan walkthrough

Use synthetic, non-sensitive sample code and targets only.

## SAST

1. Confirm MySQL, SSC, the SAST controller, and at least one worker are healthy.
2. In SSC, create a lab application and version.
3. Create the required ScanCentral controller token in SSC and enter it only
   through the wizard's protected configuration flow.
4. Obtain the matching ScanCentral client using Fortify documentation.
5. Submit a small synthetic sample, wait for completion, and verify the result
   appears under the intended SSC application version.

## DAST

1. Confirm PostgreSQL, SSC, LIM, DAST Core, and scanner readiness.
2. In LIM, install the entitled DAST license and configure the expected lab pool.
3. Choose an intentionally vulnerable target isolated inside the lab. Never scan
   public, third-party, or production systems without explicit authorization.
4. Create a minimal scan, verify scanner registration, run it, and confirm the
   result reaches the intended lab destination.

Success means an end-to-end synthetic scan is visible, not merely that pods are
Running. Remove sample results when the demo is complete.
