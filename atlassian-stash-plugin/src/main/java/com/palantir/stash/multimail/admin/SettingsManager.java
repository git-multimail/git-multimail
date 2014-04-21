package com.palantir.stash.multimail.admin;

import com.atlassian.activeobjects.external.ActiveObjects;
import com.atlassian.stash.project.Project;
import net.java.ao.DBParam;
import net.java.ao.Query;

public class SettingsManager {

    private final ActiveObjects ao;

    public SettingsManager (ActiveObjects ao) {
        this.ao = ao;
    }

    public ProjectSettings getProjectSettings (Project project) {
        ProjectSettings[] settings;
        synchronized (ao) {
            settings = ao.find(ProjectSettings.class,
                Query.select().where("PROJECT_KEY = ?", project.getKey()));
        }
        if (settings.length > 0) {
            return settings[0];
        }
        return null;
    }

    public ProjectSettings setProjectSettings (Project project, String defaultRecipients) {
        ProjectSettings[] settings;
        synchronized (ao) {
            settings = ao.find(ProjectSettings.class,
                Query.select().where("PROJECT_KEY = ?", project.getKey()));
        }
        if (settings.length > 0) {
            settings[0].setDefaultRecipients(defaultRecipients);
            settings[0].save();
            return settings[0];
        }
        synchronized (ao) {
            return ao.create(ProjectSettings.class,
                new DBParam("PROJECT_KEY", project.getKey()),
                new DBParam("DEFAULT_RECIPIENTS", defaultRecipients));
        }
    }

}
