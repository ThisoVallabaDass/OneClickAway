## SAP Basis operations
- Purpose: Technical administration of ABAP-based SAP systems.
- Scope: Routine operations, access control and software changes.

## SAP Basis responsibilities
- Platform administration: Configure SAP environments and maintain users and clients.
- Change management: Coordinate transports across development, quality assurance and production.
- Operational support: Monitor technical health and investigate errors affecting business processing.

## Three-tier ABAP architecture
- Presentation: SAP GUI or a browser provides the user interface.
- Application: Application servers execute ABAP programs and process business logic.
- Database: The database stores and retrieves the SAP system's data.

## Development, quality and production
| Environment | Main purpose |
| --- | --- |
| Development (DEV) | Create and configure changes |
| Quality assurance (QAS) | Test changes before production |
| Production (PRD) | Run live business processes |

## Routine administration
- Jobs: Check delayed or canceled jobs and review their logs.
- Spool: Resolve output errors and manage print requests.
- Clients: Maintain client settings and manage copies when required.

## Access, performance and maintenance
- Access: Maintain users, authorizations and secure administrative access.
- Performance: Review response times, workloads and system resource usage.
- Maintenance: Apply patches and investigate availability or technical errors.

## Transport process with a quality gate
- Stage 1 Release: Release changes from DEV into the QAS import queue.
- Stage 2 Test: Import into QAS and validate the changes.
- Stage 3 Approve: Complete required checks before production import.
- Stage 4 Deploy: Import approved requests into PRD in sequence.

## Conclusion: operational priorities
- Operations: Review failed jobs, access and system health.
- Changes: Test in QAS and complete approval checks before production.
- Next review: Confirm the owners and approval steps for one real transport.
