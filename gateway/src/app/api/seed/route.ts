import { NextResponse } from "next/server";
import { seedRolesAndPermissions } from "./_seed_roles";
import { seedPlaybookData } from "./_seed_playbooks";
import { seedPoliciesAndAudit } from "./_seed_policies";

export async function POST() {
  try {
    const results: string[] = [];

    // 1–3: Admin user, roles, permissions
    const { adminUserId, results: roleResults } = await seedRolesAndPermissions();
    results.push(...roleResults);

    // 4–6, 10: Servers, tools, executions, metrics
    const playbookResults = await seedPlaybookData(adminUserId);
    results.push(...playbookResults);

    // 7–9: HITL approvals, audit logs, Merkle chain
    const policyResults = await seedPoliciesAndAudit(adminUserId);
    results.push(...policyResults);

    return NextResponse.json({
      success: true,
      data: { results },
      message: "Database seeding completed (idempotent)",
    });
  } catch (error) {
    console.error("[/api/seed POST]", error);
    return NextResponse.json(
      {
        error: "Failed to seed database",
        details: error instanceof Error ? error.message : String(error),
      },
      { status: 500 }
    );
  }
}
