# Security policy

## Reporting a vulnerability

Do not open a public issue containing a vulnerability, credentials, patient
data, screenshots of patient data, or reproduction traffic. Use GitHub's
private security-advisory reporting for this repository. If private reporting
is unavailable, contact the repository owner through an established private
channel and include only the minimum technical detail needed to triage.

Reports should identify the affected component and version, impact, safe
reproduction steps, and any suggested mitigation. The maintainers will
acknowledge the report, coordinate a fix privately, and agree a disclosure
timeline before publication.

## Supported deployment boundary

The checked-in local Docker configuration is for development and synthetic
data. Patient data is supported only through the documented production profile
and the release gates in the README. A source checkout cannot by itself confer
HIPAA, GDPR, or other regulatory compliance.
