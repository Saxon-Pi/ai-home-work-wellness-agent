#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { AiHomeWorkWellnessAgentStack } from "../lib/ai-home-work-wellness-agent-stack";
import { AiHomeWorkWellnessAgentVisualizationStack } from "../lib/ai-home-work-wellness-agent-visualization-stack";

const app = new cdk.App();

new AiHomeWorkWellnessAgentStack(app, "AiHomeWorkWellnessAgentStack", {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION,
  },
});

new AiHomeWorkWellnessAgentVisualizationStack(
  app,
  "AiHomeWorkWellnessAgentVisualizationStack",
  {
    env: {
      account: process.env.CDK_DEFAULT_ACCOUNT,
      region: process.env.CDK_DEFAULT_REGION,
    },
    description: "Visualization stack for Athena + Grafana",
  }
);
