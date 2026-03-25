import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as timestream from "aws-cdk-lib/aws-timestream";

export class AiHomeWorkWellnessAgentStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

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
    // Outputs
    // =====================================================

    new cdk.CfnOutput(this, "TimestreamDatabaseName", {
      value: tsDatabase.databaseName || "wellness",
    });

    new cdk.CfnOutput(this, "TimestreamTableName", {
      value: tsTable.tableName || "room_metrics",
    });
  }
}
