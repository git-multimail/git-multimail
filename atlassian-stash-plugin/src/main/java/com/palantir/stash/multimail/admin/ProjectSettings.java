/**
 * Project settings for git multimail.
 */

package com.palantir.stash.multimail.admin;

import net.java.ao.Entity;
import net.java.ao.Preload;
import net.java.ao.schema.Default;
import net.java.ao.schema.NotNull;
import net.java.ao.schema.Table;
import net.java.ao.schema.Unique;

@Table("GMMProjectSettings")
@Preload
public interface ProjectSettings extends Entity {

    @NotNull
    @Unique
    public String getProjectKey ();
    public void setProjectKey (String value);

    public static final String DEFAULT_RECIPIENTS_DEFAULT = "none";
    @NotNull
    @Default(DEFAULT_RECIPIENTS_DEFAULT)
    public String getDefaultRecipients ();
    public void setDefaultRecipients (String value);

}
