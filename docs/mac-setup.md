# autograder セットアップガイド (Mac 向け)

本ガイドでは、Mac 上に Homebrew 経由で Colima を導入し、`autograder` プロジェクトを動かすための最短セットアップ手順を説明します。

## 1. Homebrew の導入（未導入の場合）

ターミナルアプリ（`Applications/ユーティリティ/ターミナル.app`）を開き、次を実行します。

```bash
brew --version
```

すでにインストール済みならバージョンが表示されます。「command not found」の場合は、公式インストールスクリプトを実行してください。

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

*(※ `git` が未導入の場合、この途中で「コマンドラインデベロッパツールをインストールしますか？」というダイアログが自動的に出るので「インストール」を押してください。)*

インストール完了後、画面に表示される指示（"Next steps" に出てくる `echo` 〜 `eval` のコマンド、PATHへの追加）に従ってターミナルの設定を済ませてください。完了したら一度ターミナルを閉じて開き直します。

## 2. Colima / Docker のインストール

```bash
brew install colima docker docker-compose
```

Homebrew版の `docker-compose` は、そのままでは `docker compose`（サブコマンド）として認識されません。以下のコマンドで Docker CLI のプラグインディレクトリにシンボリックリンクを作成してください。

```bash
mkdir -p ~/.docker/cli-plugins
ln -sfn "$(brew --prefix)/opt/docker-compose/bin/docker-compose" ~/.docker/cli-plugins/docker-compose
```

## 3. Colima の起動

```bash
colima start
```

初回起動時はVMイメージのダウンロードなどで数分かかります。「done」や起動完了のメッセージが出れば準備完了です。

## 4. プロジェクトの準備と実行

1. **リポジトリのクローン**
   ```bash
   git clone https://github.com/ugohsu/autograder.git
   ```

2. **ディレクトリの移動**
   ```bash
   cd autograder
   ```

3. **アプリケーションの起動**
   ```bash
   sh start.sh
   ```

   `.env` が無い場合は初回起動時に自動生成されます。しばらくするとブラウザが自動で開きます（開かない場合は `http://localhost:8000` を手動で開いてください）。

---

## トラブルシューティング

* **`Cannot connect to the Docker daemon` と出る場合:** Colimaが起動していません。`colima start` を実行してから、再度 `sh start.sh` を試してください。
* **`docker: 'compose' is not a docker command.` と出る場合:** 2で案内したシンボリックリンクの作成ができていません。上記のコマンドを実行してから、再度 `sh start.sh` を試してください。
* **Macを再起動した場合:** Colimaは自動起動しないため、再起動後は改めて `colima start` を実行してください。
* **Homebrew自体が壊れている場合（`brew`コマンドがエラーを出す、`brew doctor`で解決しない等）:** 1の公式インストールスクリプトを再実行すると、Homebrewの再インストール・修復ができます。それでも解決しない場合は、`/opt/homebrew`（Apple Silicon）または `/usr/local/Homebrew`（Intel）ごと削除してから再インストールしてください。
* **以前 Docker Desktop を導入していた場合:** ポート等が競合することがあるため、Docker Desktopを終了（またはアンインストール）してから `colima start` を試してください。
