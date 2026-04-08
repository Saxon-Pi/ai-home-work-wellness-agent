import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
//import * as timestream from "aws-cdk-lib/aws-timestream";
import * as iot from "aws-cdk-lib/aws-iot";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as events from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";

export class AiHomeWorkWellnessAgentStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // =====================================================
    // Secrets Manager
    // =====================================================

    // LINE 通知用トークン
    const lineBotSecret = new secretsmanager.Secret(this, "LineBotSecret", {
      secretName: "ai-home-work-wellness-agent/line-bot",
      description: "LINE Messaging API credentials for wellness agent",
      secretObjectValue: {
        LINE_CHANNEL_ACCESS_TOKEN: cdk.SecretValue.unsafePlainText("REPLACE_ME"),
        LINE_TO_USER_ID: cdk.SecretValue.unsafePlainText("REPLACE_ME"),
      },
    });

    // =====================================================
    // IAM Role
    // =====================================================

    // const iotToTimestreamRole = new iam.Role(this, "IotToTimestreamRole", {
    //   assumedBy: new iam.ServicePrincipal("iot.amazonaws.com"),
    // });
    // iotToTimestreamRole.addToPolicy(
    //   new iam.PolicyStatement({
    //     actions: [
    //       "timestream:WriteRecords",
    //       "timestream:DescribeEndpoints",
    //     ],
    //     resources: ["*"],
    //   })
    // );

    // =====================================================
    // Timestream
    // 25年 6月で Amazon Timestream for LiveAnalytics のアクセス終了のため使用しない
    // =====================================================

    // // Timestream Database
    // const tsDatabase = new timestream.CfnDatabase(this, "WellnessTimestreamDatabase", {
    //   databaseName: "wellness",
    // });

    // // Timestream Table
    // const tsTable = new timestream.CfnTable(this, "RoomMetricsTable", {
    //   databaseName: tsDatabase.databaseName!,
    //   tableName: "room_metrics",

    //   retentionProperties: {
    //     // memory store 保持期間 (hour)
    //     // -> 直近データを高速に扱う領域
    //     memoryStoreRetentionPeriodInHours: "24",
    //     // magnetic store 保持期間 (day)
    //     // -> 長期保存用領域
    //     magneticStoreRetentionPeriodInDays: "30",
    //   },
    // });
    // tsTable.addDependency(tsDatabase);

    // =====================================================
    // DynamoDB
    // Timestream の代替、device_id ごとの時系列データを保存する
    // =====================================================

    const metricsTable = new dynamodb.Table(this, "RoomMetricsTable", {
      tableName: "room_metrics",
      partitionKey: {
        name: "device_id",
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: {
        name: "timestamp_ms",
        type: dynamodb.AttributeType.NUMBER,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // =====================================================
    // Lambda
    // =====================================================

    // IoT Core -> DynamoDB put_item
    const ingestFn = new lambda.Function(this, "IngestLambda", {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "handler.handler",
      code: lambda.Code.fromAsset("services/ingest_lambda"),
      timeout: cdk.Duration.seconds(30),
      environment: {
        METRICS_TABLE_NAME: metricsTable.tableName,
      },
    });

    metricsTable.grantWriteData(ingestFn);

    // // Lambda に Timestream 書き込み権限を付与
    // ingestFn.addToRolePolicy(
    //   new iam.PolicyStatement({
    //     actions: [
    //       "timestream:WriteRecords",
    //       "timestream:DescribeEndpoints",
    //     ],
    //     resources: ["*"],
    //   })
    // );

    // Bedrock invoke_model
    const wellnessAgentFn = new lambda.Function(this, "WellnessAgentLambda", {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "handler.handler",
      code: lambda.Code.fromAsset("services/wellness_agent_lambda"),
      timeout: cdk.Duration.seconds(60),
      environment: {
        METRICS_TABLE_NAME: metricsTable.tableName,
        DEVICE_ID: "raspi-home-1",
        LOOKBACK_MINUTES: "60",
        BEDROCK_REGION: this.region,
        BEDROCK_MODEL_ID: "global.anthropic.claude-sonnet-4-20250514-v1:0",
        LINE_SECRET_NAME: lineBotSecret.secretName,
      },
    });

    metricsTable.grantReadData(wellnessAgentFn);
    lineBotSecret.grantRead(wellnessAgentFn);

    wellnessAgentFn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: [
          "bedrock:InvokeModel",
          "aws-marketplace:ViewSubscriptions",
          "aws-marketplace:Subscribe",
        ],
        resources: ["*"], // 検証用
      })
    );

    // =====================================================
    // EventBridge
    // =====================================================

    // AI Agent を定期実行
    const wellnessAgentScheduleRule = new events.Rule(this, "WellnessAgentScheduleRule", {
      schedule: events.Schedule.rate(cdk.Duration.minutes(30)),
    });

    wellnessAgentScheduleRule.addTarget(new targets.LambdaFunction(wellnessAgentFn));

    // =====================================================
    // IoT Core
    // =====================================================

    // トピックルールの作成 (IoT Core に届いたメッセージに対するアクション)
    const topicRuleName = "wellness_telemetry_rule";
    
    const topicRule = new iot.CfnTopicRule(this, "WellnessTelemetryRule", {
      ruleName: topicRuleName,
      topicRulePayload: {
        ruleDisabled: false,
        // rule が「どの topic を対象にするか」を SQL で定義 (rule: filter + router)
        // topic: wellness/device/+/telemetry (ワイルドカード) を対象に、
        // マッチしたら actions を実行する
        sql: "SELECT * FROM 'wellness/device/+/telemetry'",
        awsIotSqlVersion: "2016-03-23",
        actions: [
          // Ingest Lambda を起動 (Lambda内でセンサーデータをDynamoDBに書き込み)
          {
            lambda: {
            functionArn: ingestFn.functionArn,
            },
          },
        ],
      },
    });
    topicRule.node.addDependency(ingestFn);

    // IoT Core から Lambda を起動できるように permission 追加
    ingestFn.addPermission("AllowIoTInvokeLambda", {
      principal: new iam.ServicePrincipal("iot.amazonaws.com"),
      action: "lambda:InvokeFunction",
      sourceArn: `arn:aws:iot:${this.region}:${this.account}:rule/${topicRuleName}`,
    });

    // =====================================================
    // Outputs
    // =====================================================
    new cdk.CfnOutput(this, "MetricsTableName", {
      value: metricsTable.tableName,
    });

    new cdk.CfnOutput(this, "IoTRuleName", {
      value: topicRuleName,
    });

    new cdk.CfnOutput(this, "IotTelemetryTopic", {
      value: "wellness/device/raspi-home-1/telemetry",
    });

    new cdk.CfnOutput(this, "IngestLambdaName", {
      value: ingestFn.functionName,
    });

    new cdk.CfnOutput(this, "WellnessAgentLambdaName", {
      value: wellnessAgentFn.functionName,
    });

    new cdk.CfnOutput(this, "WellnessAgentSchedule", {
      value: "rate(30 minutes)",
    });
  }
}
