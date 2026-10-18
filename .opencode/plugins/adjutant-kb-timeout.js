import { spawnSync } from "node:child_process"

const PREFIX = /^\s*ADJUTANT_PARENT_OPERATION_ID=(op-[a-z0-9]+)\s+/
const KB_COMMAND = /^(?:bash\s+)?(?:\.\/)?adjutant\s+kb\s+(?:query|write|query-all|cross-query)(?:\s|$)/

export function hasShellComposition(command) {
  let singleQuoted = false
  let doubleQuoted = false
  let escaped = false
  for (let index = 0; index < command.length; index += 1) {
    const char = command[index]
    const next = command[index + 1]
    if (escaped) {
      escaped = false
      continue
    }
    if (char === "\\" && !singleQuoted) {
      escaped = true
      continue
    }
    if (char === "'" && !doubleQuoted) {
      singleQuoted = !singleQuoted
      continue
    }
    if (char === '"' && !singleQuoted) {
      doubleQuoted = !doubleQuoted
      continue
    }
    if (singleQuoted) continue
    if (char === "`" || (char === "$" && next === "(")) return true
    if (!doubleQuoted && ("|;&\n\r".includes(char))) return true
  }
  return singleQuoted || doubleQuoted || escaped
}

export const AdjutantKbTimeout = async ({ directory }) => ({
  "tool.execute.before": async (input, output) => {
    if (input.tool !== "bash" || typeof output.args?.command !== "string") return

    const command = output.args.command
    const prefix = command.match(PREFIX)
    if (!prefix || !KB_COMMAND.test(command.slice(prefix[0].length))) return
    if (hasShellComposition(command)) {
      throw new Error(
        "Extended KB timeout requires one standalone Adjutant KB command without shell composition.",
      )
    }

    const helper = spawnSync(
      "./adjutant",
      ["operation-context", prefix[1], "--session-id", input.sessionID],
      { cwd: directory, encoding: "utf8", timeout: 5000 },
    )
    if (helper.status !== 0) {
      const reason = (helper.stderr || helper.stdout || "operation context rejected").trim()
      throw new Error(`Cannot extend KB timeout: ${reason}`)
    }
    const context = JSON.parse(helper.stdout)
    if (!Number.isInteger(context.timeout_ms) || context.timeout_ms < 1000) {
      throw new Error("Cannot extend KB timeout: helper returned an invalid budget")
    }

    output.args.timeout = context.timeout_ms
    output.args.command = command.replace(
      prefix[0],
      `ADJUTANT_PARENT_OPERATION_ID=${prefix[1]} ` +
        `ADJUTANT_ORIGIN_SESSION_ID=${input.sessionID} ` +
        `ADJUTANT_ORIGIN_TOOL_CALL_ID=${input.callID} `,
    )
  },
})
