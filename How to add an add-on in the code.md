In order to add another add-on, you must do the following change.

# aqt/addons.py

Add your add-on to the set of add-ons.

# addons

In this folder, put a copy of the add-on, as it is in ankiweb when it
was added to this folder.

# differences.md

List your add-on in the list of change between this fork and regular
anki. Add the add-on number after the title.

# Configuration options

If there are options to configure, add the buttons to
designer/preferences.ui

A checkbox is done as follow:
```xml
       <item>
        <widget class="QCheckBox" name="NAME">
         <property name="text">
          <string>TEXT</string>
         </property>
        </widget>
       </item>
```

A text as follows:
```xml
        <item>
         <widget class="QLabel" name="label_12">
          <property name="text">
           <string>TEXT</string>
          </property>
          <property name="wordWrap">
           <bool>true</bool>
          </property>
         </widget>
        </item>
```

They should be added between
```xml
           <string>&lt;html&gt;&lt;head/&gt;&lt;body&gt;&lt;p&gt;&lt;span style=&quot; font-weight:600;&quot;&gt;Extra&lt;/span&gt;&lt;br/&gt;Those options are not documented in anki's manual. They allow to configure the different add-ons incorporated in this special version of anki.&lt;/p&gt;&lt;/body&gt;&lt;/html&gt;</string>
          </property>
          <property name="wordWrap">
           <bool>true</bool>
          </property>
         </widget>
        </item>
```
and
```xml
        <item>
         <spacer name="verticalSpacer">
          <property name="orientation">
           <enum>Qt::Vertical</enum>
           ```

## Editing configuration
In `aqt.preferences` you should edit `setupExtra`, adding:
``` python
        self.form.xMLName.setChecked(
            self.prof.get("xMLName", DefaultVale))
```
and `updateExtra`, adding:
```
        self.prof["xMLName"] = self.form.xMLName.isChecked()
```

You can access this value from anywhere in the code by
```Python
    from aqt import mw
    mw.pm.profile.get("xMLName", DefaultVale)
```

## Git
Add baseFork as upstream of the branch.
```bash
git remote add upstream baseFork
