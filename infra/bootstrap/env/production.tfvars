# Production, same account as staging: the OIDC provider already exists after the
# staging apply, production builds nothing and plans nothing on pull requests.
app_name                      = "agent-factory"
stage                         = "production"
github_repository             = "ivikash/agent-factory"
primary_region                = "us-west-2"
regions                       = ["us-west-2", "us-east-1"]
deploy_target                 = "terraform"
artifact_kind                 = "zip"
is_build_account              = false
artifact_consumer_account_ids = []
create_oidc_provider          = false
create_plan_role              = false
