import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import {
  fileURLToPath,
} from "node:url";


const here = path.dirname(
  fileURLToPath(import.meta.url)
);

const frontendRoot =
  path.resolve(here, "..");

function read(relativePath) {
  return fs.readFileSync(
    path.join(
      frontendRoot,
      relativePath
    ),
    "utf8"
  )
    .replace(/\r\n/g, "\n")
    .replace(/\r/g, "\n");
}


test(
  "messages use premium role-aware surfaces",
  () => {
    const source = read(
      "src/components/Chat/Message.jsx"
    );

    assert.ok(
      source.includes(
        "data-chat-message="
      )
    );

    assert.ok(
      source.includes(
        'data-message-surface="premium"'
      )
    );

    assert.ok(
      source.includes(
        '"You"'
      )
    );

    assert.ok(
      source.includes(
        '"Onkar AI"'
      )
    );
  }
);


test(
  "message redesign preserves all existing actions",
  () => {
    const source = read(
      "src/components/Chat/Message.jsx"
    );

    for (
      const behavior of [
        "copyText",
        "saveBookmark",
        "removeBookmark",
        "speak",
        "startEditing",
        "regenerateFromMessage",
        "createConversationBranch",
        "deleteCurrentMessage",
      ]
    ) {
      assert.ok(
        source.includes(behavior),
        `Missing message behavior: ${behavior}`
      );
    }
  }
);


test(
  "composer uses the premium workspace shell",
  () => {
    const source = read(
      "src/components/Chat/MessageInput.jsx"
    );

    assert.ok(
      source.includes(
        'data-workspace-composer="v2.39"'
      )
    );

    assert.ok(
      source.includes(
        'data-composer-input-row="primary"'
      )
    );

    assert.ok(
      source.includes(
        "rounded-[26px]"
      )
    );
  }
);


test(
  "composer preserves agent file voice and send behavior",
  () => {
    const source = read(
      "src/components/Chat/MessageInput.jsx"
    );

    for (
      const behavior of [
        'id="agentPicker"',
        'id="fileUpload"',
        "onChange={uploadFile}",
        "startListening",
        "stopListening",
        "sendMessage()",
        "onClick={sendMessage}",
      ]
    ) {
      assert.ok(
        source.includes(behavior),
        `Missing composer behavior: ${behavior}`
      );
    }

    assert.ok(
      source.includes(
        'accept=".pdf,image/*"'
      )
    );

    assert.ok(
      source.includes(
        "multiple"
      )
    );
  }
);


test(
  "composer keeps safe send gating and theme behavior",
  () => {
    const source = read(
      "src/components/Chat/MessageInput.jsx"
    );

    assert.ok(
      source.includes(
        "const canSend ="
      )
    );

    assert.ok(
      source.includes(
        "disabled={!canSend}"
      )
    );

    assert.ok(
      source.includes(
        'theme === "dark"'
      )
    );
  }
);


test(
  "chat chrome uses only the existing react-icons dependency",
  () => {
    const source = read(
      "src/components/Chat/MessageInput.jsx"
    );

    assert.ok(
      source.includes(
        'from "react-icons/fi"'
      )
    );

    const packageJson =
      JSON.parse(
        read("package.json")
      );

    assert.ok(
      Object.prototype.hasOwnProperty.call(
        packageJson.dependencies,
        "react-icons"
      )
    );
  }
);
