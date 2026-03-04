#!/usr/bin/env python3
"""
Analyze potential cost savings from sharing ECS cluster and infrastructure
between Multimodal Librarian and CollaborativeEditor applications.
"""

import boto3
import json
from datetime import datetime

def analyze_shared_infrastructure_savings():
    """Analyze cost savings from sharing ECS cluster and infrastructure."""
    
    print("Analyzing Shared Infrastructure Cost Savings...")
    print("=" * 60)
    
    # Current infrastructure costs (monthly estimates)
    current_costs = {
        "multimodal_librarian": {
            "ecs_cluster": 0,  # ECS clusters are free, but tasks cost
            "ecs_tasks": 50,   # 2 tasks * $25/month each (2 vCPU, 4GB)
            "load_balancer": 16.20,  # ALB $16.20/month base
            "nat_gateway": 32.40,    # Already optimized to $0 with sharing
            "cloudfront": 1.00,      # Minimal usage
            "security_groups": 0,    # Free
            "iam_roles": 0,          # Free
            "cloudwatch_logs": 5,    # Log storage and retention
            "secrets_manager": 2,    # 3 secrets * $0.40/month
            "kms": 1,               # KMS key usage
            "waf": 5,               # WAF web ACL
            "total": 0
        },
        "collaborative_editor": {
            "ecs_cluster": 0,
            "ecs_tasks": 25,        # 1 task * $25/month (estimated)
            "load_balancer": 16.20,
            "nat_gateway": 32.40,   # Current NAT Gateway
            "cloudfront": 1.00,
            "security_groups": 0,
            "iam_roles": 0,
            "cloudwatch_logs": 3,
            "secrets_manager": 1,
            "kms": 1,
            "waf": 5,
            "total": 0
        }
    }
    
    # Calculate current totals
    for app in current_costs:
        current_costs[app]["total"] = sum(
            v for k, v in current_costs[app].items() if k != "total"
        )
    
    total_current = sum(app["total"] for app in current_costs.values())
    
    print("CURRENT INFRASTRUCTURE COSTS (Monthly)")
    print("-" * 40)
    for app_name, costs in current_costs.items():
        print(f"\n{app_name.replace('_', ' ').title()}:")
        for service, cost in costs.items():
            if service != "total":
                print(f"  {service.replace('_', ' ').title()}: ${cost:.2f}")
        print(f"  TOTAL: ${costs['total']:.2f}")
    
    print(f"\nCURRENT TOTAL MONTHLY COST: ${total_current:.2f}")
    
    # Shared infrastructure costs
    shared_costs = {
        "shared_infrastructure": {
            "ecs_cluster": 0,       # Single shared cluster (free)
            "ecs_tasks": 75,        # Combined tasks (no reduction in compute)
            "load_balancer": 16.20, # Single shared ALB
            "nat_gateway": 32.40,   # Single shared NAT Gateway
            "cloudfront": 2.00,     # Combined usage (minimal increase)
            "security_groups": 0,   # Shared security groups (free)
            "iam_roles": 0,         # Shared IAM roles (free)
            "cloudwatch_logs": 6,   # Combined logs (slight increase)
            "secrets_manager": 2.5, # Combined secrets (slight increase)
            "kms": 1,              # Shared KMS key
            "waf": 5,              # Single shared WAF
            "total": 0
        }
    }
    
    shared_costs["shared_infrastructure"]["total"] = sum(
        v for k, v in shared_costs["shared_infrastructure"].items() if k != "total"
    )
    
    total_shared = shared_costs["shared_infrastructure"]["total"]
    monthly_savings = total_current - total_shared
    annual_savings = monthly_savings * 12
    
    print("\n" + "=" * 60)
    print("SHARED INFRASTRUCTURE COSTS (Monthly)")
    print("-" * 40)
    print("\nShared Infrastructure:")
    for service, cost in shared_costs["shared_infrastructure"].items():
        if service != "total":
            print(f"  {service.replace('_', ' ').title()}: ${cost:.2f}")
    print(f"  TOTAL: ${total_shared:.2f}")
    
    print("\n" + "=" * 60)
    print("COST SAVINGS ANALYSIS")
    print("-" * 40)
    print(f"Current Monthly Cost: ${total_current:.2f}")
    print(f"Shared Monthly Cost:  ${total_shared:.2f}")
    print(f"Monthly Savings:      ${monthly_savings:.2f}")
    print(f"Annual Savings:       ${annual_savings:.2f}")
    print(f"Savings Percentage:   {(monthly_savings/total_current)*100:.1f}%")
    
    # Detailed savings breakdown
    print("\n" + "=" * 60)
    print("DETAILED SAVINGS BREAKDOWN")
    print("-" * 40)
    
    savings_breakdown = {
        "Load Balancer": 16.20,  # Eliminate one ALB
        "CloudWatch Logs": 2.0,  # Slight consolidation
        "Secrets Manager": 0.5,  # Slight consolidation
        "Management Overhead": 1.0,  # Reduced operational complexity
    }
    
    for item, savings in savings_breakdown.items():
        print(f"{item}: ${savings:.2f}/month")
    
    print("\n" + "=" * 60)
    print("SHARED INFRASTRUCTURE BENEFITS")
    print("-" * 40)
    print("✅ Cost Savings:")
    print(f"   - Monthly: ${monthly_savings:.2f}")
    print(f"   - Annual: ${annual_savings:.2f}")
    print("\n✅ Operational Benefits:")
    print("   - Single ECS cluster to manage")
    print("   - Shared security groups and IAM roles")
    print("   - Consolidated monitoring and logging")
    print("   - Simplified deployment pipelines")
    print("   - Reduced infrastructure complexity")
    
    print("\n✅ Technical Benefits:")
    print("   - Better resource utilization")
    print("   - Shared auto-scaling policies")
    print("   - Common networking configuration")
    print("   - Unified security policies")
    
    print("\n" + "=" * 60)
    print("IMPLEMENTATION CONSIDERATIONS")
    print("-" * 40)
    print("🔧 Required Changes:")
    print("   - Merge ECS task definitions")
    print("   - Configure shared ALB with multiple target groups")
    print("   - Update service discovery configuration")
    print("   - Consolidate IAM roles and policies")
    
    print("\n⚠️  Considerations:")
    print("   - Applications share compute resources")
    print("   - Need proper resource isolation")
    print("   - Shared failure domain (cluster-level issues affect both)")
    print("   - Requires coordination for cluster updates")
    
    print("\n🎯 Recommended Approach:")
    print("   - Start with shared ALB and networking")
    print("   - Gradually consolidate other resources")
    print("   - Maintain separate task definitions initially")
    print("   - Monitor resource utilization closely")
    
    # Save results
    results = {
        "analysis_date": datetime.now().isoformat(),
        "current_costs": current_costs,
        "shared_costs": shared_costs,
        "savings": {
            "monthly": monthly_savings,
            "annual": annual_savings,
            "percentage": (monthly_savings/total_current)*100
        },
        "savings_breakdown": savings_breakdown
    }
    
    with open(f"shared-infrastructure-analysis-{int(datetime.now().timestamp())}.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📊 Analysis saved to: shared-infrastructure-analysis-{int(datetime.now().timestamp())}.json")
    
    return results

if __name__ == "__main__":
    try:
        results = analyze_shared_infrastructure_savings()
        print(f"\n✅ Analysis completed successfully!")
        print(f"💰 Potential monthly savings: ${results['savings']['monthly']:.2f}")
        print(f"💰 Potential annual savings: ${results['savings']['annual']:.2f}")
        
    except Exception as e:
        print(f"❌ Error during analysis: {str(e)}")
        exit(1)