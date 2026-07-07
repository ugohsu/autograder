# autograder セットアップガイド (Windows / WSL2 向け)

本ガイドでは、Windows 上で WSL2 (Debian) を使用し、`autograder` プロジェクトを動かすための最短セットアップ手順を説明します。

## 1. WSL2 の導入

Windows のターミナル（PowerShell）を「管理者として実行」し、以下のコマンドを入力して Debian をインストールします。

```powershell
wsl --install -d Debian
```

※インストール完了後、自動的に開くウィンドウの指示に従ってユーザー名とパスワードを設定してください。

## 2. 必須ツールのインストール

Debian のターミナル内で、最初にパッケージリストを更新し、`curl` と `git` をインストールします。

```bash
sudo apt update
sudo apt install curl git -y
```

## 3. Docker のインストール

Docker公式のインストールスクリプトを実行して、最新の Docker を導入します。

```bash
curl -fsSL https://get.docker.com | sh
```

*(※ 実行中に「WSL環境では Docker Desktop を推奨する」という警告文と20秒間の待機時間が発生しますが、そのまま無視して待っていれば自動でインストールが完了します。)*

## 4. Docker の権限設定

毎回 `sudo` を付けずに Docker を操作できるように、現在のユーザーをグループに追加します。

```bash
sudo usermod -aG docker $USER
```

**重要:** ここまで終わったら、権限設定を反映させるために一度ターミナルを閉じ、PowerShell で以下を実行して WSL を完全に再起動してください。

```powershell
wsl --shutdown
```

## 5. プロジェクトの準備と実行

再度 Debian のターミナルを起動し、リポジトリの取得とアプリケーションの起動を行います。

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

   `.env` が無い場合は初回起動時に自動生成されます。

---

## トラブルシューティング

* **Docker が動かない場合:** WSL起動直後にDockerデーモンが立ち上がっていない場合があります。その際は `sudo service docker start` を実行してから、再度 `sh start.sh` を試してください。
* **Permission denied と出る場合:** 4の手順（グループ追加とWSL再起動）が正しく完了しているか確認してください。
