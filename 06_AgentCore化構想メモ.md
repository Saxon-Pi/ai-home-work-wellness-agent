# AgentCore化構想メモ

- [AgentCore化構想メモ](#agentcore化構想メモ)
- [AgentCore化の目的](#agentcore化の目的)
- [AgentCore化のゴール](#agentcore化のゴール)
- [今回の AgentCore化対象](#今回の-agentcore化対象)
- [移行方針](#移行方針)

---

# AgentCore化の目的
- Agent実行基盤をマネージド化する
- ツール連携を標準化する
- 将来的な Memory / Identity / Observability 拡張に備える

---

# AgentCore化のゴール
本プロジェクトでは、以下の段階的移行を目指す  
※ 現行のシステムでも安定稼働できているため、今回は Step1 の Gateway のみを対象とする

## Step1: ツール実行基盤を AgentCore Gateway に移行 (ゴール)
👉 ツール呼び出しの標準化・管理・セキュリティをマネージドに寄せるため  

現在 mcpServerFn で Lambda Invoke により実行しているツール群を、  
AgentCore Gateway のツールとして登録し、Agent から直接呼び出せる構成に移行する  

## Step2: Agent 実行を Runtime へ移行 (オプション)
chat_agent Lambda / wellness_agent Lambda を AgentCore Runtime に移行する  
```
現在:
Lambda 上で Strands Agent を実行
  ↓
Bedrock Claude を呼ぶ

AgentCore Runtime化:
AgentCore Runtime 上で Agent アプリを実行
  ↓
Bedrock Claude などのモデルを呼ぶ
```

## Step3: Memory / Observability を追加検討 (オプション)
Agentシステムの **監視 / メトリクス可視化 / デバッグ** 機能を強化する  

👉 AgentCore Observability は CloudWatch ベースのダッシュボードやテレメトリで、  
　 セッション数、レイテンシ、実行時間、トークン使用量、エラー率などを見るための機能

AWS 公式ドキュメント:  
[Observe your agent applications on Amazon Bedrock AgentCore Observability](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html)

---

# 今回の AgentCore化対象
上記を踏まえて、このフェーズで実装する内容は以下となる  

実装対象:  
- **AgentCore Gateway**: mcpServerFn のツール群を管理・公開する方法を検証・実装する

実装対象外:  
- **AgentCore Runtime**: Agent 実行基盤の移行は将来検討する
- **AgentCore Observability**: 監視強化は将来検討する
- **AgentCore Memory / Identity**: 必要になった段階で検討する

---

# 移行方針
- 現行構成を残す
- AgentCore Gatewayから既存mcpServerFnを呼ぶ
- ツール単位で段階的に Gateway へ切り替える
- 動作確認後、Runtime移行を検討

---

