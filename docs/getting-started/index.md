# Getting started

Use this path when you are new to the repository or want to create a fresh lab.

1. Read the [lab and demo use boundary](../lab-use.md). The wizard requires an
   explicit acknowledgement before deployment.
2. Review the host, browser, license, and registry prerequisites in the
   repository [README](https://github.com/treisland/fortifylab#prerequisites).
3. Follow the README [quick start](https://github.com/treisland/fortifylab#quick-start)
   and choose **Guided deployment (recommended)** in `start_wizard.sh`.
4. Use [deployment and lifecycle guidance](../operations/deployment-and-lifecycle.md)
   to understand safe resume, retry, start, and destroy behavior.
5. Configure [networking and TLS](../operations/networking-and-tls.md), then
   open the application URLs printed by the wizard.

The wizard's [offline Help Center](../help/README.md) remains available before
MicroK8s starts and while the lab is unhealthy. It is the right fallback when
the online documentation cannot be reached.

!!! warning "Use synthetic data only"

    Do not use production credentials, source, customer data, or scan results.
    This single-node lab is for evaluation, demonstrations, and training.
