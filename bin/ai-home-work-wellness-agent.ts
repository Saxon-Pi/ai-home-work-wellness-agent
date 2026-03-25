#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { AiHomeWorkWellnessAgentStack } from "../lib/ai-home-work-wellness-agent-stack";

const app = new cdk.App();

new AiHomeWorkWellnessAgentStack(app, "AiHomeWorkWellnessAgentStack", {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION,
  },
});
