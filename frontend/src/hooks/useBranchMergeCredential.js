import {
  useCallback,
  useState,
} from "react";


function useBranchMergeCredential() {
  const [credential, setCredentialState] =
    useState("");

  const rememberCredential = useCallback(
    (value) => {
      setCredentialState(
        typeof value === "string" ? value : ""
      );
    },
    []
  );

  const forgetCredential = useCallback(() => {
    setCredentialState("");
  }, []);

  return {
    credential,
    hasCredential: credential.length > 0,
    rememberCredential,
    forgetCredential,
  };
}


export default useBranchMergeCredential;
