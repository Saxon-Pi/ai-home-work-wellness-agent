/*
SCD40 から受信したデータを可視化するための Grafana 環境構築用スタック
データ可視化は AI Agent システムとは直接関係しないため別スタックで構築する
*/

import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as grafana from "aws-cdk-lib/aws-grafana";
import * as iam from "aws-cdk-lib/aws-iam";

export class AiHomeWorkWellnessAgentVisualizationStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // S3 バケット (Athenaクエリ結果の保存先)
    const athenaResultsBucket = new s3.Bucket(this, "AthenaResultsBucket", {
      bucketName: `ai-home-work-wellness-athena-results`,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    /*
    Grafana Workspace の authenticationProviders: ["AWS_SSO"] にする場合、
    IAM Identity Center の有効化が必要
    今回はデータの一時的な可視化目的のため、Grafana Workspace はコンソールから作成する
    */

    // // Grafana が Athena / Glue / S3 を参照するための IAM ロール
    // const grafanaWorkspaceRole = new iam.Role(this, "GrafanaWorkspaceRole", {
    //   assumedBy: new iam.ServicePrincipal("grafana.amazonaws.com"),
    //   description: "Role for Amazon Managed Grafana to query Athena and related resources",
    // });
    // grafanaWorkspaceRole.addToPolicy(
    //   new iam.PolicyStatement({
    //     actions: [
    //       "athena:ListDataCatalogs",
    //       "athena:ListDatabases",
    //       "athena:ListTableMetadata",
    //       "athena:GetDatabase",
    //       "athena:GetDataCatalog",
    //       "athena:GetTableMetadata",
    //       "athena:StartQueryExecution",
    //       "athena:GetQueryExecution",
    //       "athena:GetQueryResults",
    //       "athena:StopQueryExecution",
    //       "glue:GetDatabases",
    //       "glue:GetDatabase",
    //       "glue:GetTables",
    //       "glue:GetTable",
    //       "glue:GetPartitions",
    //       "s3:ListBucket",
    //       "s3:GetObject",
    //       "s3:PutObject",
    //       "s3:AbortMultipartUpload",
    //       "s3:ListMultipartUploadParts",
    //       "s3:ListBucketMultipartUploads",
    //     ],
    //     resources: ["*"],
    //   })
    // );

    // // Grafana ワークスペース
    // const workspace = new grafana.CfnWorkspace(this, "GrafanaWorkspace", {
    //   name: "ai-home-work-wellness-grafana",
    //   accountAccessType: "CURRENT_ACCOUNT",
    //   authenticationProviders: ["AWS_SSO"],
    //   permissionType: "CUSTOMER_MANAGED",
    //   roleArn: grafanaWorkspaceRole.roleArn,
    //   dataSources: ["ATHENA"],
    //   description: "Visualization workspace for ai-home-work-wellness-agent",
    //   notificationDestinations: [],
    // });

    // Outputs
    new cdk.CfnOutput(this, "AthenaResultsBucketName", {
      value: athenaResultsBucket.bucketName,
    });

    // new cdk.CfnOutput(this, "GrafanaWorkspaceId", {
    //   value: workspace.attrId,
    // });

    // new cdk.CfnOutput(this, "GrafanaWorkspaceEndpoint", {
    //   value: workspace.attrEndpoint,
    // });

  }
}
