# Staging: the build account. Single-account layout, so production is the same
# account and no consumer ids are needed.
app_name                      = "agent-factory"
stage                         = "staging"
github_repository             = "ivikash/agent-factory"
primary_region                = "us-west-2"
regions                       = ["us-west-2", "us-east-1"]
deploy_target                 = "terraform"
artifact_kind                 = "zip"
is_build_account              = true
artifact_consumer_account_ids = []
create_oidc_provider          = true
create_plan_role              = true
