// Role limits shown in the UI (ticket 18: visible, not merely enforced).
// Mirrors services/lifemate_cloud/roles.py; the API remains authoritative.
import type { AppRole } from "./types.ts";

export interface RoleLimits {
  role: AppRole;
  label: string;
  canSubmit: boolean;
  canCancel: boolean;
  canManageArtifacts: boolean;
  canApprove: boolean;
  canSetCostPolicy: boolean;
  summary: string;
}

export const ROLE_LIMITS: Readonly<Record<AppRole, Omit<RoleLimits, "role">>> = {
  owner: {
    label: "Owner",
    canSubmit: true,
    canCancel: true,
    canManageArtifacts: true,
    canApprove: true,
    canSetCostPolicy: true,
    summary: "Controls approvals and cost policy; may submit, cancel and manage artifacts.",
  },
  maintainer: {
    label: "Maintainer",
    canSubmit: true,
    canCancel: true,
    canManageArtifacts: true,
    canApprove: true,
    canSetCostPolicy: false,
    summary: "Manages and approves artifacts; may submit and cancel runs.",
  },
  researcher: {
    label: "Researcher",
    canSubmit: true,
    canCancel: true,
    canManageArtifacts: false,
    canApprove: false,
    canSetCostPolicy: false,
    summary: "Submits and cancels permitted experiments; cannot approve artifacts or cost policy.",
  },
  viewer: {
    label: "Viewer",
    canSubmit: false,
    canCancel: false,
    canManageArtifacts: false,
    canApprove: false,
    canSetCostPolicy: false,
    summary: "Reads approved metadata only.",
  },
};

export function roleLimits(role: AppRole): RoleLimits {
  return { role, ...ROLE_LIMITS[role] };
}
