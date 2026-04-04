# Grafana データ可視化手順書

## 目的
SCD40 と接続したラズパイから送信 → DynamoDB に登録されたセンサーデータを  
Amazon Managed Grafana を使用してグラフに表示する

------------------------------------------------------------------------

## 構成概要
```mermaid
flowchart LR
RaspberryPi --> IoTCore --> Lambda --> DynamoDB --> Athena --> Grafana
```
※ Raspberry Pi 3 Model B V1.2 使用

------------------------------------------------------------------------

## 前提
Athena 実行結果格納用 S3 バケットを作成していること  
※ 後の設定で必要なため、空の prefix を作成しておく  
![S3bucket](./img/grafana/0.png)

------------------------------------------------------------------------

## ステップ
1. Athena DynamoDB コネクタ作成
2. Athena 動作確認
3. Grafana Workspace 作成
4. Grafanaログイン
5. Athena データソース追加
6. ダッシュボード作成

------------------------------------------------------------------------

## Step1. Athena DynamoDB コネクタ作成
左のメニューから **データソースとカタログ** を選択し、
**データソースの作成** をクリックする  
![データソースとカタログ](./img/grafana/1.png)

**Amazon DynamoDB** を選択し、**次へ** をクリックする  
![データソース選択](./img/grafana/2.png)

**データソース名**、**Amazon S3 内の流出場所** を入力し、**次へ** をクリックする  
※ S3 は prefix まで指定が必要  
![データソース詳細](./img/grafana/3.png)

データソースが正常に作成されることを確認する  
![データソース作成](./img/grafana/5.png)

------------------------------------------------------------------------

## Step2. Athena 動作確認
以下のクエリを実行し、DynamoDBのデータを取得できれば成功  
```sql
SELECT *
FROM "dynamodb_datasource"."room_metrics"
LIMIT 10;
```
![クエリ実行](./img/grafana/6.png)

------------------------------------------------------------------------

## Step3. Grafana Workspace 作成
トップページから **ワークスペースを作成** をクリックする  
![Grafanaトップページ](./img/grafana/7.png)

**ワークスペース名** を入力して **次へ** をクリックする  
![ワークスペースの詳細](./img/grafana/8.png)

**認証アクセス** では **AWS IAM ID センター** を選択する  
![認証アクセス](./img/grafana/9.png)

Grafana にログインするためのユーザを作成する  
![ユーザ作成](./img/grafana/10.png)

他の項目はデフォルトのまま進み、**ワークスペースを作成** をクリックする  
![ワークスペース作成](./img/grafana/11.png)

ワークスペースの作成が完了する  
```log
Your account is not a member of an organization.
```
というエラーが出る場合は、後続のログインユーザとパスワードの設定を行う  
![ワークスペース作成結果](./img/grafana/12.png)

### ユーザ認証基盤の設定
#### ① IAM Identity Center ユーザ登録
AWS から IAM Identity Center の招待メールが来ている場合は  
**Accept invitation** をクリックしてユーザ登録を行う  
![ワークスペース作成](./img/grafana/13.png)

パスワードを作成し、サインインに成功すれば完了  
※ これにより、IAM Identity Center にログインするための認証情報が作成される
![ワークスペース作成](./img/grafana/14.png)

#### ② Grafana ユーザ割り当て
ワークスペース上で以下のメッセージが表示される場合は、  
```log
IAM ID センターユーザーまたはユーザーグループが割り当てられていません。
```
**新しいユーザーまたはグループの割り当て** をクリックする  
![ワークスペース](./img/grafana/15.png)

ワークグループ作成時に作成したユーザを選択し、**ユーザーとグループを割り当て** をクリックする    
![ユーザ選択](./img/grafana/16.png)

ユーザが登録されていれば完了  
![ユーザ](./img/grafana/17.png)

------------------------------------------------------------------------

## Step4. Grafanaログイン
ワークスペースに表示されている **Grafana ワークスペース URL** にアクセスし、  
**Sign in with AWS IAM Identity Center** をクリックし、Grafana にサインインする  
![Grafanaサインイン](./img/grafana/18.png)

IAM Identity Center の認証情報を入力し、**サインイン** をクリックする  
![パスワード入力](./img/grafana/19.png)

Grafana のトップページにアクセスできれば、サインイン成功となる
![Grafanaトップページ](./img/grafana/20.png)

------------------------------------------------------------------------

## Step5. Athena データソース追加
Grafana のデータソースに Athena を追加し、ダッシュボードにデータを描画する　　

### 前提
Grafana のユーザのユーザタイプが **管理者** であること  
ユーザを選択して **アクション** から **管理者を作成する** を選択すると管理者に変更できる  
![ユーザタイプ](./img/grafana/21.png)

ワークスペースの **データソース** タブから **Amazon Athena** がアタッチされていない場合は、  
選択後に **アクション** からアタッチを有効化する  
![データソース](./img/grafana/22.png)

**ワークスペース設定オプション** から **プラグイン管理** の **編集** に進み、  
![プラグイン管理1](./img/grafana/23.png)
**プラグイン管理をオンにする** にチェックを入れて **変更の保存** をクリックする  
![プラグイン管理2](./img/grafana/24.png)

### Data sources 設定
左側のメニューの **Connections** から **Add new connection** を選択し、  
**Amazon Athena** をクリックする  
![connection](./img/grafana/25.png)

Athena をインストールする  
※ ここで以下のメッセージが表示される場合は、**前提** に記載した設定を確認すること  
```log
You do not have permission to install this plugin.
```
![install1](./img/grafana/26.png)
![install2](./img/grafana/27.png)

以下の項目を設定し、**Save & test** が成功すれば完了  
- Name：データソース名（**default** は有効化）
- Authentication Provider：**Worksoace IAM Role** のままで OK
- Default Region：ap-northeast-1
- Data source：作成した Athena のデータソース名
- Database：default
- Workgroup：primary
- Output Location：Athena のクエリの結果格納先 S3 prefix

![settings1](./img/grafana/28.png)
![settings2](./img/grafana/29.png)
------------------------------------------------------------------------

## Step6. ダッシュボード作成
