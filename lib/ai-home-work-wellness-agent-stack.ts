import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as timestream from "aws-cdk-lib/aws-timestream";
import * as iot from "aws-cdk-lib/aws-iot";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";

export class AiHomeWorkWellnessAgentStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

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
    // =====================================================

    // Timestream Database
    const tsDatabase = new timestream.CfnDatabase(this, "WellnessTimestreamDatabase", {
      databaseName: "wellness",
    });

    // Timestream Table
    const tsTable = new timestream.CfnTable(this, "RoomMetricsTable", {
      databaseName: tsDatabase.databaseName!,
      tableName: "room_metrics",

      retentionProperties: {
        // memory store 保持期間 (hour)
        // -> 直近データを高速に扱う領域
        memoryStoreRetentionPeriodInHours: "24",
        // magnetic store 保持期間 (day)
        // -> 長期保存用領域
        magneticStoreRetentionPeriodInDays: "30",
      },
    });
    tsTable.addDependency(tsDatabase);

    // =====================================================
    // Lambda
    // =====================================================

    const ingestFn = new lambda.Function(this, "IngestLambda", {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "handler.handler",
      code: lambda.Code.fromAsset("services/ingest_lambda"),
      environment: {
        TIMESTREAM_DATABASE_NAME: tsDatabase.databaseName!,
        TIMESTREAM_TABLE_NAME: tsTable.tableName!,
      },
    });

    // Lambda に Timestream 書き込み権限を付与
    ingestFn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: [
          "timestream:WriteRecords",
          "timestream:DescribeEndpoints",
        ],
        resources: ["*"],
      })
    );

    // =====================================================
    // IoT Core
    // =====================================================

    // トピックルールの作成 (IoT Core に届いたメッセージに対するアクション)
    const topicRule = new iot.CfnTopicRule(this, "WellnessTelemetryRule", {
      topicRulePayload: {
        ruleDisabled: false,
        // rule が「どの topic を対象にするか」を SQL で定義 (rule: filter + router)
        // topic: wellness/device/+/telemetry (ワイルドカード) を対象に、
        // マッチしたら actions を実行する
        sql: "SELECT * FROM 'wellness/device/+/telemetry'",
        awsIotSqlVersion: "2016-03-23",
        actions: [
          // Ingest Lambda を起動 (Lambda内でセンサーデータをTimestreamに書き込み)
          {
            lambda: {
            functionArn: ingestFn.functionArn,
            },
          },
        ],
      },
    });
    topicRule.node.addDependency(tsTable);

    // IoT Core から Lambda を起動できるように permission 追加
    ingestFn.addPermission("AllowIoTInvokeLambda", {
      principal: new iam.ServicePrincipal("iot.amazonaws.com"),
      action: "lambda:InvokeFunction",
      sourceArn: `arn:aws:iot:${this.region}:${this.account}:rule/WellnessTelemetryRule`,
    });

    // =====================================================
    // Outputs
    // =====================================================

    new cdk.CfnOutput(this, "TimestreamDatabaseName", {
      value: tsDatabase.databaseName || "wellness",
    });

    new cdk.CfnOutput(this, "TimestreamTableName", {
      value: tsTable.tableName || "room_metrics",
    });

    new cdk.CfnOutput(this, "IotTelemetryTopic", {
      value: "wellness/device/raspi-home-1/telemetry",
    });
  }
}
