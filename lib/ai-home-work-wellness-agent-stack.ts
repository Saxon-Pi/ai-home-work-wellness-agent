import * as fs from "fs";
import * as path from "path";
import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as iot from "aws-cdk-lib/aws-iot";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as events from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as apigwv2 from "aws-cdk-lib/aws-apigatewayv2";
import * as integrations from "aws-cdk-lib/aws-apigatewayv2-integrations";

//import * as timestream from "aws-cdk-lib/aws-timestream";

// config/local.json からパラメータを取得
function readLocalConfig() {
  const configPath = path.join(__dirname, "..", "config", "local.json");
  if (!fs.existsSync(configPath)) {
    return {};
  }
  return JSON.parse(fs.readFileSync(configPath, "utf-8"));
}

const localConfig = readLocalConfig();
const agentcoreGatewayUrl =
  localConfig.agentcoreGatewayUrl ?? "REPLACE_ME_AGENTCORE_GATEWAY_URL";


export class AiHomeWorkWellnessAgentStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // =====================================================
    // Secrets Manager
    // =====================================================

    // デプロイ → コンソールからシークレットの登録 が必要
    // LINE 通知用トークン
    const lineBotSecret = new secretsmanager.Secret(this, "LineBotSecret", {
      secretName: "ai-home-work-wellness-agent/line-chat-bot",
      description: "LINE Messaging API credentials for wellness agent",
      secretObjectValue: {
        LINE_CHANNEL_ACCESS_TOKEN: cdk.SecretValue.unsafePlainText("REPLACE_ME"),
        LINE_TO_USER_ID: cdk.SecretValue.unsafePlainText("REPLACE_ME"),
      },
    });

    // Google Calendar 用トークン
    const googleCalendarSecret = new secretsmanager.Secret(this, "GoogleCalendarOAuthSecret", {
      secretName: "ai-home-work-wellness-agent/google-calendar-oauth",
      description: "Google Calendar OAuth credentials for chat agent",
      secretObjectValue: {
        GOOGLE_CLIENT_ID: cdk.SecretValue.unsafePlainText("REPLACE_ME"),
        GOOGLE_CLIENT_SECRET: cdk.SecretValue.unsafePlainText("REPLACE_ME"),
        GOOGLE_REFRESH_TOKEN: cdk.SecretValue.unsafePlainText("REPLACE_ME"),
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
    // =====================================================

    // Timestream の代替、device_id ごとの時系列データを保存する
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

    // 室内環境ステータス保存用テーブル（Agentを実行するかの判定に使用する）
    const agentStateTable = new dynamodb.Table(this, "WellnessAgentStateTable", {
      tableName: "wellness_agent_state",
      partitionKey: {
        name: "device_id",
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // =====================================================
    // S3
    // =====================================================

    // Athena クエリ結果とグラフ画像格納用バケット
    const reportArtifactsBucket = new s3.Bucket(this, "ReportArtifactsBucket", {
      bucketName: undefined,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // =====================================================
    // Athena
    // =====================================================

    /* 
      データソース作成と権限周りで沼ったので Grafana 用に作成したデータソースを流用する
      作成手順は　Grafanaデータ可視化手順書.md　を参照
    */

    // // Athena の DB Connector はコンソールから作成する
    // // Amazon Athena > データソースとカタログ > データソースの作成
    // // - データソースを選択: Amazon DynamoDB
    // // - データソース名: dynamodb_datasource_report2
    // // - Glue Data Catalog IAM role: arn:aws:iam::<account-id>:role/<AthenaDynamoDataSourceRoleの名称>
    // // - Amazon S3: s3://aihomeworkwellnessagentst-reportartifactsbucket219-zpdmzth7yhfj/athena-results

    // // Lake Formation 絡みでデータソース作成が失敗する場合は、ユーザとロールを admin 登録する
    // // Lake Formation > Administrative roles and tasks > Data lake administrators

    // const athenaDynamoDataSourceRole = new iam.Role(this, "AthenaDynamoDataSourceRole", {
    //   assumedBy: new iam.CompositePrincipal(
    //     new iam.ServicePrincipal("athena.amazonaws.com"),
    //     new iam.ServicePrincipal("lakeformation.amazonaws.com"),
    //   ),
    // });
    // metricsTable.grantReadData(athenaDynamoDataSourceRole);
    // reportArtifactsBucket.grantReadWrite(athenaDynamoDataSourceRole);

    // athenaDynamoDataSourceRole.addToPolicy(
    //   new iam.PolicyStatement({
    //     actions: ["s3:ListBucket", "s3:GetBucketLocation"],
    //     resources: [reportArtifactsBucket.bucketArn],
    //   })
    // );

    // athenaDynamoDataSourceRole.addToPolicy(
    //   new iam.PolicyStatement({
    //     actions: [
    //       "s3:GetObject",
    //       "s3:PutObject",
    //       "s3:DeleteObject",
    //     ],
    //     resources: [`${reportArtifactsBucket.bucketArn}/*`],
    //   })
    // );

    // =====================================================
    // AgentCore
    // =====================================================
    /*
    今回は既存のCDK構成を残して、一部ツールを AgentCore Gateway に移行することが目的のため、
    AgentCore CLI ベースで Gateway 作成を実施した
    実施手順は以下ドキュメントを参照すること
    - 06_AgentCore化構想メモ.md (# ツールの AgentCore Gateway化 手順)
    */

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

    // Agent の tool に使用する共通ロジックレイヤ (core.py)
    const commonLayer = new lambda.LayerVersion(this, "CommonPythonLayer", {
      code: lambda.Code.fromAsset("layer"),
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_12],
      description: "Shared common python modules",
    });

    // Strands Agent 用の Lambda layer
    const strandsLayer = lambda.LayerVersion.fromLayerVersionArn(
      this,
      "StrandsAgentsLayer",
      "arn:aws:lambda:ap-northeast-1:856699698935:layer:strands-agents-py3_12-x86_64:1"
    );

    // Wellness Agent (Strands Agent): Agent定期実行 / ツール呼び出し判断 / LINE通知
    const wellnessAgentFn = new lambda.Function(this, "WellnessAgentLambda", {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "handler.handler",
      code: lambda.Code.fromAsset("services/wellness_agent"),
      timeout: cdk.Duration.seconds(90),
      memorySize: 512,
      layers: [strandsLayer, commonLayer],
      environment: {
        METRICS_TABLE_NAME: metricsTable.tableName,
        AGENT_STATE_TABLE_NAME: agentStateTable.tableName,
        DEVICE_ID: "raspi-home-1",
        LOOKBACK_MINUTES: "60",
        BEDROCK_REGION: this.region,
        BEDROCK_MODEL_ID: "global.anthropic.claude-sonnet-4-20250514-v1:0",
        LINE_SECRET_NAME: lineBotSecret.secretName,
        AGENTCORE_GATEWAY_URL: agentcoreGatewayUrl,
      },
    });

    metricsTable.grantReadData(wellnessAgentFn);
    agentStateTable.grantReadWriteData(wellnessAgentFn);
    lineBotSecret.grantRead(wellnessAgentFn);

    wellnessAgentFn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
        ],
        resources: ["*"], // TODO: 権限絞る
      })
    );

    wellnessAgentFn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: [
          "aws-marketplace:ViewSubscriptions",
          "aws-marketplace:Subscribe",
        ],
        resources: ["*"],
      })
    );

    // Chat Agent (Strands Agent): Agent実行 / ツール呼び出し判断 / LINE返信
    const lineChatHandlerFn = new lambda.Function(this, "LineChatHandlerLambda", {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "handler.handler",
      code: lambda.Code.fromAsset("services/chat_agent"),
      timeout: cdk.Duration.seconds(90),
      memorySize: 512,
      layers: [strandsLayer, commonLayer],
      environment: {
        METRICS_TABLE_NAME: metricsTable.tableName,
        AGENT_STATE_TABLE_NAME: agentStateTable.tableName,
        DEVICE_ID: "raspi-home-1",
        LOOKBACK_MINUTES: "60",
        BEDROCK_REGION: this.region,
        BEDROCK_MODEL_ID: "global.anthropic.claude-sonnet-4-20250514-v1:0",
        LINE_SECRET_NAME: lineBotSecret.secretName,
        AGENTCORE_GATEWAY_URL: agentcoreGatewayUrl,
      },
    });

    metricsTable.grantReadData(lineChatHandlerFn);
    agentStateTable.grantReadWriteData(lineChatHandlerFn);
    lineBotSecret.grantRead(lineChatHandlerFn);

    lineChatHandlerFn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
        ],
        resources: ["*"], // TODO: 権限絞る
      })
    );

    lineChatHandlerFn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: [
          "aws-marketplace:ViewSubscriptions",
          "aws-marketplace:Subscribe",
        ],
        resources: ["*"],
      })
    );

    // MCP Server: weather / calendar / report のツール実行主体
    const mcpServerFn = new lambda.Function(this, "McpServerLambda", {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "handler.handler",
      code: lambda.Code.fromAsset("services/mcp_server"),
      timeout: cdk.Duration.seconds(90),
      memorySize: 1024,
      layers: [commonLayer],
      environment: {
        METRICS_TABLE_NAME: metricsTable.tableName,
        AGENT_STATE_TABLE_NAME: agentStateTable.tableName,
        DEVICE_ID: "raspi-home-1",
        LOOKBACK_MINUTES: "60",
        GOOGLE_CALENDAR_SECRET_NAME: googleCalendarSecret.secretName,
        WEATHER_LATITUDE: "35.703085",   // 緯度 (吉祥寺駅)
        WEATHER_LONGITUDE: "139.579775", // 経度 (吉祥寺駅)
        ATHENA_CATALOG: "dynamodb_datasource",
        ATHENA_DATABASE: "default",
        ATHENA_TABLE: "room_metrics",
        ATHENA_OUTPUT_LOCATION: `s3://${reportArtifactsBucket.bucketName}/athena-results/`,
        REPORT_BUCKET_NAME: reportArtifactsBucket.bucketName,
        MPLCONFIGDIR: "/tmp/matplotlib",
      },
    });

    metricsTable.grantReadData(mcpServerFn);
    agentStateTable.grantReadWriteData(mcpServerFn);
    googleCalendarSecret.grantRead(mcpServerFn);
    reportArtifactsBucket.grantReadWrite(mcpServerFn);

    mcpServerFn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: [
          "athena:StartQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
          "athena:GetDataCatalog",
          "athena:ListDataCatalogs",
          "athena:ListDatabases",
          "athena:ListTableMetadata",
          "athena:GetTableMetadata",
          "athena:GetWorkGroup",
        ],
        resources: ["*"],
      })
    );

    mcpServerFn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: [
          "glue:GetDatabase",
          "glue:GetTable",
          "glue:GetPartitions",
          "glue:GetPartition",
        ],
        resources: ["*"],
      })
    );

    // Athena の dynamodb_datasource が裏で Federated Query connector Lambda 呼ぶため追加
    mcpServerFn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: [
          "lambda:InvokeFunction",
        ],
        resources: ["*"], // TODO: DynamoDB connector Lambda の ARN に絞る
      })
    );

    // bucket.grantReadWrite だと ListBucket は含まれないことがあるため追加
    mcpServerFn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["s3:ListBucket"],
        resources: [reportArtifactsBucket.bucketArn],
      })
    );

    // lineChatHandlerFn が mcpServerFn を呼び出す
    mcpServerFn.grantInvoke(lineChatHandlerFn);
    
    lineChatHandlerFn.addEnvironment(
      "MCP_SERVER_FUNCTION_NAME",
      mcpServerFn.functionName
    );

    // wellnessAgentFn が mcpServerFn を呼び出す
    mcpServerFn.grantInvoke(wellnessAgentFn);
    
    wellnessAgentFn.addEnvironment(
      "MCP_SERVER_FUNCTION_NAME",
      mcpServerFn.functionName
    );

    // =====================================================
    // API Gateway
    // =====================================================

    // LINE の Webhook 用 API Gateway (チャット応答Agent用)
    const lineWebhookApi = new apigwv2.HttpApi(this, "LineWebhookApi", {
      apiName: "line-webhook-api",
    });

    lineWebhookApi.addRoutes({
      path: "/webhook",
      methods: [apigwv2.HttpMethod.POST],
      integration: new integrations.HttpLambdaIntegration(
        "LineWebhookIntegration",
        lineChatHandlerFn
      ),
    });

    // =====================================================
    // EventBridge
    // =====================================================

    // AI Agent を定期実行 (JST: 9:00 ~ 23:00、10分間隔)
    const wellnessAgentScheduleRuleDay = new events.Rule(this, "WellnessAgentScheduleRuleDay", {
      schedule: events.Schedule.cron({
        minute: "0/10",
        hour: "0-13",
      }),
    });
    const wellnessAgentScheduleRuleLast = new events.Rule(this, "WellnessAgentScheduleRuleLast", {
      schedule: events.Schedule.cron({
        minute: "0",
        hour: "14",
      }),
    });
    wellnessAgentScheduleRuleDay.addTarget(new targets.LambdaFunction(wellnessAgentFn));
    wellnessAgentScheduleRuleLast.addTarget(new targets.LambdaFunction(wellnessAgentFn));

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
      value: "JST 9:00-23:00 every 10 minutes",
    });

    new cdk.CfnOutput(this, "LineWebhookUrl", {
      value: `${lineWebhookApi.apiEndpoint}/webhook`,
    });
  }
}
