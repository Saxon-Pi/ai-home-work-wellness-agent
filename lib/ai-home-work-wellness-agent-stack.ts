import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as timestream from "aws-cdk-lib/aws-timestream";
import * as iot from "aws-cdk-lib/aws-iot";
import * as iam from "aws-cdk-lib/aws-iam";

export class AiHomeWorkWellnessAgentStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // =====================================================
    // IAM Role
    // =====================================================

    const iotToTimestreamRole = new iam.Role(this, "IotToTimestreamRole", {
      assumedBy: new iam.ServicePrincipal("iot.amazonaws.com"),
    });
    iotToTimestreamRole.addToPolicy(
      new iam.PolicyStatement({
        actions: [
          "timestream:WriteRecords",
          "timestream:DescribeEndpoints",
        ],
        resources: ["*"],
      })
    );

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
    // IoT Core
    // =====================================================

    // トピックルールの作成 (IoT Core に届いたメッセージに対するアクション)
    const topicRule = new iot.CfnTopicRule(this, "WellnessTelemetryRule", {
      topicRulePayload: {
        ruleDisabled: false,
        // rule が「どの topic を対象にするか」を SQL で定義
        // topic: wellness/device/+/telemetry (ワイルドカード使用可)
        sql: "SELECT * FROM 'wellness/device/+/telemetry'",
        awsIotSqlVersion: "2016-03-23",
        actions: [
          // Timestream テーブルにデータを送信
          // measures (温度/湿度/二酸化炭素濃度) の 送信は Lambda で実装
          {
            timestream: {
              roleArn: iotToTimestreamRole.roleArn,
              databaseName: tsDatabase.databaseName!,
              tableName: tsTable.tableName!,
              dimensions: [
                {
                  name: "device_id", // デバイスID (ラズパイ)
                  value: "${device_id}",
                },
              ],
              timestamp: {
                unit: "MILLISECONDS",
                value: "${timestamp_ms}", 
              },
            },
          },
        ],
      },
    });
    topicRule.node.addDependency(tsTable);

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
