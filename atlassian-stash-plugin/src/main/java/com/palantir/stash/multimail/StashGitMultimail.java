package com.palantir.stash.multimail;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.PrintStream;
import java.util.Collection;
import java.util.Map;

import org.slf4j.Logger;

import com.atlassian.stash.hook.repository.AsyncPostReceiveRepositoryHook;
import com.atlassian.stash.hook.repository.RepositoryHookContext;
import com.atlassian.stash.repository.RefChange;
import com.atlassian.stash.repository.Repository;
import com.atlassian.stash.server.ApplicationPropertiesService;
import com.atlassian.stash.setting.RepositorySettingsValidator;
import com.atlassian.stash.setting.Settings;
import com.atlassian.stash.setting.SettingsValidationErrors;
import com.atlassian.stash.user.StashAuthenticationContext;
import com.atlassian.stash.user.StashUser;
import com.palantir.stash.multimail.logger.PluginLoggerFactory;

/**
 * Note that hooks can implement SettingsValidator directly.
 */
public class StashGitMultimail implements AsyncPostReceiveRepositoryHook, RepositorySettingsValidator {

    private final ApplicationPropertiesService appService;
    private final StashAuthenticationContext authContext;
    private final String git_multimail_script;
    private final String email_script;
    private final Logger logger;

    public StashGitMultimail(ApplicationPropertiesService appService,
                             StashAuthenticationContext authContext,
                             PluginLoggerFactory logger) {
        this.appService = appService;
        this.authContext = authContext;
        this.git_multimail_script = initializeScript("git_multimail");
        this.email_script = initializeScript("send_emails");
        this.logger = logger.getLogger(this.getClass().toString());
    }

    private String initializeScript(String resource_name) {
        // Write git_multimail.py out to disk somewhere that we can find
        // and execute it.
        final ClassLoader classLoader = this.getClass().getClassLoader();

        // Read the file in, then write it back out to a temporary file.
        // It's incredibly annoying that we can't just get the absolute
        // path to the file so we don't have to do these shenanigans, but
        // I couldn't find a way to do that.  The classLoader.getResource()
        // call only returned a string of the form
        //    bundle://89.0:1/scripts/git_multimail.py
        final InputStream pyStream = classLoader.getResourceAsStream("scripts/"+resource_name+".py");
        java.util.Scanner s = new java.util.Scanner(pyStream).useDelimiter("\\A");
        String pyContents = s.hasNext() ? s.next() : "";
        File f;
        try {
            f = File.createTempFile(resource_name, ".py");
            BufferedWriter output = new BufferedWriter(new FileWriter(f));
            output.write(pyContents);
            output.close();
            return f.getAbsolutePath();
        } catch (IOException e) {
            // What can we do, other than log the fact that we
            // can't send the email out?
            logger.error("Unable to initialize git multimail plugin", e);
            return "/dev/null";
        }
    }

    /**
     * Connects to a configured URL to notify of all changes.
     */
    @Override
    public void postReceive(RepositoryHookContext context, Collection<RefChange> refChanges) {

        String email_addresses = context.getSettings().getString("email_addresses");
        if (email_addresses == null) {
            // Nothing to do, since there's no one to email
            return;
        }

        // Determine the name of the user doing the updates, and the
        // repository being updated, (i.e. who is pushing and where
        // they are pushing to).
        StashUser user = authContext.getCurrentUser();
        String submitter = user.getDisplayName() + " <" + user.getEmailAddress() + ">";

        Repository repo = context.getRepository();
        String reponame = repo.getProject().getKey() + "/" + repo.getSlug();

        // Determine any branches we are filtering on
        String ref_filter_regex = context.getSettings().getString("ref_filter_regex", "");
        Boolean reverse_regex = context.getSettings().getBoolean("reverse_regex", false);

        // Create the process
        ProcessBuilder pb = new ProcessBuilder("python2", email_script,
                                               git_multimail_script,
                                               "--recipients", email_addresses,
                                               reverse_regex ? "--ref-filter-inclusion-regex" : "--ref-filter-exclusion-regex", ref_filter_regex,
                                               "--stash-user", submitter,
                                               "--stash-repo", reponame);

        // Environment setup...
        Map<String, String> env = pb.environment();
        env.remove("USER");  // USER == "stash"; not so helpful to us
        env.put("GIT_DIR", appService.getRepositoryDir(repo).getAbsolutePath());

        // Start the process
        Process pr;
        try {
            pr = pb.start();
        } catch (IOException e) {
            // What can we do, other than log the fact that we can't
            // send the email out?
            logger.error("Unable to send emails", e);
            return;
        }

        // Give it the necessary refs on stdin
        OutputStream pr_stdin = pr.getOutputStream();
        PrintStream pr_stdin_stream = new PrintStream(pr_stdin);
        for (RefChange r : refChanges) {
            pr_stdin_stream.format("%s %s %s\n", r.getFromHash(),
                                   r.getToHash(), r.getRefId());
        }
        pr_stdin_stream.close();

        // Wait for the process to finish
        int ret = 42;
        try {
            ret = pr.waitFor();
        } catch (InterruptedException e) {
            // JVM shutdown or something?  Just bail but log the occurrence
            // for anyone wanting to do something fancy
            logger.error("Execution of {} interrupted!\n", email_script);
            return;
        }

        // Report any errors; return status, stderr, & stdout
        if (ret != 0) {
            logger.error("Return status of {} is {}\n", email_script, ret);

            InputStream pr_stderr = pr.getErrorStream();
            java.util.Scanner s = new java.util.Scanner(pr_stderr).useDelimiter("\\A");
            logger.error("Stderr is: " + (s.hasNext() ? s.next() : ""));

            InputStream pr_stdout = pr.getInputStream();
            s = new java.util.Scanner(pr_stdout).useDelimiter("\\A");
            logger.error("Stdout is: " + (s.hasNext() ? s.next() : ""));
        }
    }

    @Override
    public void validate(Settings settings, SettingsValidationErrors errors,
                         Repository repository) {
        if (settings.getString("email_addresses", "").isEmpty()) {
            errors.addFieldError("email_addresses",
                                 "Email address field is blank, please supply one");

        String ref_filter_regex = settings.getString("ref_filter_regex", "");
        if (ref_filter_regex.isEmpty()) {
            return;
        }

        String pycommand = String.format("import re; exec('try: \\n  re.compile(\\\"%s\\\")\\nexcept re.error as e:\\n  raise SystemExit(e.message)')", ref_filter_regex);

        // Start the process
        Process pr;
        try {
            pr = new ProcessBuilder("python2", "-c", pycommand).start();
        } catch (IOException e) {
            // Not sure what to do other than point out we can't execute python to verify
            errors.addFieldError("ref_filter_regex",
                                 "Unable to execute python2 to verify Ref Filter Regex");
            return;
        }

        // Wait for the process to finish
        int ret = 42;
        try {
            ret = pr.waitFor();
        } catch (InterruptedException e) {
            // JVM shutdown or something?  Just bail and inform the user.
            errors.addFieldError("ref_filter_regex",
                                 "Unable to execute python2 to verify Ref Filter Regex");
            return;
        }

        // Report any errors; return status, stderr, & stdout
        if (ret != 0) {
            InputStream pr_stderr = pr.getErrorStream();
            java.util.Scanner s = new java.util.Scanner(pr_stderr).useDelimiter("\\A");
            errors.addFieldError("ref_filter_regex",
                                 "Ref Filter Regex is bad: "+(s.hasNext() ? s.next() : ""));
        }
    }
}
