/**
 * Multimail project settings configuration servlet.
 */

package com.palantir.stash.multimail.admin;

import com.atlassian.soy.renderer.SoyTemplateRenderer;
import com.atlassian.stash.exception.AuthorisationException;
import com.atlassian.stash.project.*;
import com.atlassian.stash.server.ApplicationPropertiesService;
import com.atlassian.stash.user.*;
import com.atlassian.stash.util.Operation;
import com.google.common.collect.ImmutableMap;
import com.palantir.stash.multimail.logger.PluginLoggerFactory;
import java.io.IOException;
import java.net.URI;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.regex.Pattern;
import javax.servlet.*;
import javax.servlet.http.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class ProjectSettingsServlet extends HttpServlet {

    private final Logger log;

    private final ApplicationPropertiesService propertiesService;

    private final SettingsManager settingsManager;

    private final PermissionValidationService validationService;

    private final ProjectService projectService;

    private final SecurityService securityService;

    private final SoyTemplateRenderer soyTemplateRenderer;

    public ProjectSettingsServlet (
            PluginLoggerFactory loggerFactory,
            ApplicationPropertiesService propertiesService,
            SettingsManager settingsManager,
            PermissionValidationService validationService,
            ProjectService projectService,
            SecurityService securityService,
            SoyTemplateRenderer soyTemplateRenderer) {
        this.log = loggerFactory.getLogger(this.getClass().toString());
        this.propertiesService = propertiesService;
        this.settingsManager = settingsManager;
        this.validationService = validationService;
        this.projectService = projectService;
        this.securityService = securityService;
        this.soyTemplateRenderer = soyTemplateRenderer;
    }

    // Make sure the current user is authenticated
    private boolean verifyLoggedIn (HttpServletRequest req, HttpServletResponse resp)
            throws IOException {
        try {
            validationService.validateAuthenticated();
        } catch (AuthorisationException notLoggedInException) {
            try {
                resp.sendRedirect(propertiesService.getLoginUri(URI.create(req.getRequestURL() +
                    (req.getQueryString() == null ? "" : "?" + req.getQueryString())
                )).toASCIIString());
            } catch (Exception e) {
                log.error("Unable to redirect unauthenticated user to login page", e);
            }
            return false;
        }
        return true;
    }

    // Make sure the current user is a project admin
    private boolean verifyProjectAdmin (HttpServletRequest req, HttpServletResponse resp,
            Project project) throws IOException {
        try {
            validationService.validateForProject(project, Permission.PROJECT_ADMIN);
        } catch (AuthorisationException notProjectAdminException) {
            log.warn("User {} is not a project administrator of {}",
                req.getRemoteUser(), project.getKey());
            resp.sendError(HttpServletResponse.SC_UNAUTHORIZED, "You do not have permission to access this page.");
            return false;
        }
        return true;
    }

    private void renderPage (HttpServletRequest req, HttpServletResponse resp,
            Project project, ProjectSettings projectSettings,
            Collection<? extends Object> errors) throws ServletException, IOException {
        resp.setContentType("text/html");
        try {
            if (projectSettings == null) {
                projectSettings = settingsManager.setProjectSettings(
                    project, ProjectSettings.DEFAULT_RECIPIENTS_DEFAULT);
            }
            ImmutableMap<String, Object> data = new ImmutableMap.Builder<String, Object>()
                .put("project", project)
                .put("settings", projectSettings)
                .put("errors", errors)
                .build();
            soyTemplateRenderer.render(resp.getWriter(),
                "com.palantir.stash.stash-git-multimail:multimail-soy",
                "plugin.page.multimail.projectSettingsPage",
                data);
        } catch (Exception e) {
            log.error("Error rendering Soy template", e);
        }
    }

    @Override
    protected void doGet (HttpServletRequest req, HttpServletResponse resp)
            throws ServletException, IOException {
        if (!verifyLoggedIn(req, resp)) {
            return;
        }
        Project project = getProject(req);
        if (project == null) {
            resp.sendError(HttpServletResponse.SC_NOT_FOUND, "Project not found.");
            return;
        }
        if (verifyProjectAdmin(req, resp, project)) {
            renderPage(req, resp, project, settingsManager.getProjectSettings(project),
                Collections.emptyList());
        }
    }

    @Override
    protected void doPost (HttpServletRequest req, HttpServletResponse resp)
            throws ServletException, IOException {
        if (!verifyLoggedIn(req, resp)) {
            return;
        }
        Project project = getProject(req);
        if (project == null) {
            resp.sendError(HttpServletResponse.SC_NOT_FOUND, "Project not found.");
            return;
        }
        if (!verifyProjectAdmin(req, resp, project)) {
            return;
        }

        // Parse arguments
        ArrayList<String> errors = new ArrayList<String>();
        String defaultRecipients = req.getParameter("defaultRecipients");

        // Update settings object iff no parse errors
        ProjectSettings settings;
        if (errors.isEmpty()) {
            settings = settingsManager.setProjectSettings(project, defaultRecipients);
        } else {
            settings = settingsManager.getProjectSettings(project);
        }

        renderPage(req, resp, project, settings, errors);
    }

    private Project getProject (HttpServletRequest req) {
        String uri = req.getRequestURI();
        String[] uriParts = uri.split("/");
        if (uriParts.length < 1) {
            return null;
        }
        return projectService.findByKey(uriParts[uriParts.length - 1]);
    }

}
